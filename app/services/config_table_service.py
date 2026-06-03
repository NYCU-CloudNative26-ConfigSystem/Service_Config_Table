import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher

import httpx
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.company import Company
from app.models.config_table import CT, GT, ConfigRelation, ConfigRelationUser
from app.models.project import Project, ProjectTemplateVersion
from app.schemas.config_table import (
    CTRowResponse,
    ConfigApprovalResponse,
    ConfigEntrySchema,
    ConfigHistoryItem,
    ConfigPromoteByUuidRequest,
    ConfigPromoteRequest,
    ConfigReadResponse,
    ConfigWriteRequest,
    GroupEntrySchema,
    ReviewSimilarityCandidate,
    ReviewSimilarityEntryMatch,
    ReviewSimilarityReport,
    ReviewSimilaritySourceEntry,
)

logger = logging.getLogger(__name__)


class ConfigTableService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _slugify(text: str) -> str:
        """Replace whitespace runs with underscores and strip non-word characters."""
        text = text.strip()
        text = re.sub(r"\s+", "_", text)
        text = re.sub(r"[^\w\-]", "", text)
        return text

    @staticmethod
    def _strip_ref(ref: str) -> str:
        if ref.startswith("VALUE:") or ref.startswith("GROUP:"):
            return ref[6:]
        return ref

    @staticmethod
    def _normalize_text(text: str | None) -> str:
        return re.sub(r"\s+", " ", (text or "").strip()).lower()

    @staticmethod
    def _text_similarity(left: str | None, right: str | None) -> float:
        left_norm = ConfigTableService._normalize_text(left)
        right_norm = ConfigTableService._normalize_text(right)
        if not left_norm or not right_norm:
            return 0.0
        return SequenceMatcher(None, left_norm, right_norm).ratio()

    async def _ssot_get_json(self, path: str, token: str, params: dict[str, str] | None = None):
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"{settings.ssot_service_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            return response.json()

    async def _resolve_ssot_node(self, node_uuid: str, token: str, node_cache: dict[str, dict | None]) -> dict | None:
        if node_uuid in node_cache:
            return node_cache[node_uuid]
        try:
            node = await self._ssot_get_json(f"/api/v1/node/{node_uuid}", token)
        except httpx.HTTPError as exc:
            logger.warning("Failed to resolve SSOT node %s: %s", node_uuid, exc)
            node = None
        node_cache[node_uuid] = node
        return node

    async def _resolve_display_value(
        self,
        ref: str,
        token: str,
        node_cache: dict[str, dict | None],
        depth: int = 0,
    ) -> str:
        if depth > 6:
            return "…"

        node = await self._resolve_ssot_node(self._strip_ref(ref), token, node_cache)
        if not node:
            return ref

        node_type = node.get("type")
        if node_type == "value":
            if node.get("is_sensitive"):
                return "(sensitive)"
            return str(node.get("val") or "")
        if node_type == "name":
            return str(node.get("name_val") or ref)
        if node_type == "group":
            entries = node.get("entries") or []
            if not entries:
                return "[]" if node.get("isArray") else "{}"
            parts: list[str] = []
            for entry in entries:
                key_node = await self._resolve_ssot_node(str(entry.get("key")), token, node_cache)
                key_display = str(key_node.get("name_val") or entry.get("key")) if key_node and key_node.get("type") == "name" else str(entry.get("key"))
                value_display = await self._resolve_display_value(str(entry.get("val")), token, node_cache, depth + 1)
                parts.append(f"{key_display}: {value_display}")
            return f"[ {', '.join(parts)} ]" if node.get("isArray") else f"{{ {', '.join(parts)} }}"
        return ref

    async def _flatten_config_rows(
        self,
        rows: list[CTRowResponse],
        token: str,
        node_cache: dict[str, dict | None],
    ) -> list[dict[str, str | bool]]:
        flattened: list[dict[str, str | bool]] = []

        async def visit_row(key_uuid: str, value_ref: str, path_parts: list[str]) -> None:
            key_node = await self._resolve_ssot_node(key_uuid, token, node_cache)
            key_alias = str(key_node.get("name_val") or key_uuid) if key_node and key_node.get("type") == "name" else key_uuid
            next_path = path_parts + [key_alias]

            value_node = await self._resolve_ssot_node(self._strip_ref(value_ref), token, node_cache)
            if value_node and value_node.get("type") == "group":
                flattened.append({
                    "path": " › ".join(next_path),
                    "key_uuid": key_uuid,
                    "key_alias": key_alias,
                    "value_ref": value_ref,
                    "value_display": await self._resolve_display_value(value_ref, token, node_cache),
                    "is_group": True,
                })
                for entry in value_node.get("entries") or []:
                    await visit_row(str(entry.get("key")), str(entry.get("val")), next_path)
                return

            flattened.append({
                "path": " › ".join(next_path),
                "key_uuid": key_uuid,
                "key_alias": key_alias,
                "value_ref": value_ref,
                "value_display": await self._resolve_display_value(value_ref, token, node_cache),
                "is_group": False,
            })

        for row in rows:
            await visit_row(row.key, row.val, [])

        return flattened

    async def _build_default_name(self, proj_id: str, cmp_id: str) -> str:
        proj_result = await self.db.execute(select(Project).where(Project.proj_id == proj_id))
        proj = proj_result.scalar_one_or_none()
        cmp_result = await self.db.execute(select(Company).where(Company.cmp_id == cmp_id))
        cmp = cmp_result.scalar_one_or_none()
        proj_label = self._slugify(proj.display_name if proj else proj_id)
        cmp_label = self._slugify(cmp.display_name if cmp else cmp_id)
        date_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
        return f"{proj_label}_{cmp_label}_{date_str}"

    async def write_config(self, payload: ConfigWriteRequest) -> ConfigReadResponse:
        name = payload.name.strip() if payload.name and payload.name.strip() else None
        if not name:
            name = await self._build_default_name(payload.proj_id, payload.cmp_id)

        # New config_relation starts as pending — approval required before it becomes latest
        cr = ConfigRelation(
            proj_id=payload.proj_id,
            cmp_id=payload.cmp_id,
            environment=payload.environment,
            template_version_uuid=payload.template_version_uuid,
            latest=False,
            approval_status="pending",
            change_description=payload.change_description,
            promoted_from_uuid=payload.source_snapshot_uuid,
            name=name,
        )
        self.db.add(cr)
        await self.db.flush()  # get cr.uuid

        # Junction row
        self.db.add(ConfigRelationUser(config_relation_uuid=cr.uuid, user_id=payload.user_id))

        # CT rows + recursive GT rows
        ct_rows: list[CT] = []
        for entry in payload.entries:
            ct = CT(config_relation_uuid=cr.uuid, key=entry.key, val=entry.val)
            self.db.add(ct)
            ct_rows.append(ct)
            if entry.group_entries:
                self._insert_gt_rows(entry.group_entries)

        await self.db.commit()
        await self.db.refresh(cr)

        logger.info("Config written: config_relation=%s proj=%s cmp=%s", cr.uuid, payload.proj_id, payload.cmp_id)

        return ConfigReadResponse(
            config_relation_uuid=cr.uuid,
            date_created=cr.date_created,
            environment=cr.environment,
            rows=[CTRowResponse(uuid=ct.uuid, key=ct.key, val=ct.val) for ct in ct_rows],
            name=cr.name,
        )

    def _insert_gt_rows(self, entries: list[GroupEntrySchema]) -> None:
        for entry in entries:
            self.db.add(GT(gid=entry.gid, key=entry.key, val=entry.val))
            if entry.group_entries:
                self._insert_gt_rows(entry.group_entries)

    async def promote_config(self, payload: ConfigPromoteRequest, user_id: str) -> ConfigReadResponse:
        now = datetime.now(timezone.utc)

        # Fetch source latest
        src_result = await self.db.execute(
            select(ConfigRelation).where(
                ConfigRelation.proj_id == payload.proj_id,
                ConfigRelation.cmp_id == payload.cmp_id,
                ConfigRelation.environment == payload.from_environment,
                ConfigRelation.latest == True,  # noqa: E712
            )
        )
        source = src_result.scalar_one_or_none()
        if source is None:
            raise LookupError(
                f"No config found in '{payload.from_environment}' to promote"
            )

        # Fetch source CT rows
        ct_result = await self.db.execute(
            select(CT).where(CT.config_relation_uuid == source.uuid)
        )
        source_rows = list(ct_result.scalars().all())

        # Soft-delete previous latest in target environment
        await self.db.execute(
            update(ConfigRelation)
            .where(
                ConfigRelation.proj_id == payload.proj_id,
                ConfigRelation.cmp_id == payload.cmp_id,
                ConfigRelation.environment == payload.to_environment,
                ConfigRelation.latest == True,  # noqa: E712
            )
            .values(latest=False, date_deleted=now)
        )

        # New config_relation for target environment — auto-approved (source was already vetted)
        new_cr = ConfigRelation(
            proj_id=payload.proj_id,
            cmp_id=payload.cmp_id,
            environment=payload.to_environment,
            template_version_uuid=source.template_version_uuid,
            latest=True,
            approval_status="approved",
            approved_by=user_id,
            approved_at=now,
            promoted_from_uuid=source.uuid,
        )
        self.db.add(new_cr)
        await self.db.flush()

        self.db.add(ConfigRelationUser(config_relation_uuid=new_cr.uuid, user_id=user_id))

        # Copy CT rows — GT rows are keyed by gid (not config_relation_uuid) so they remain valid
        new_ct_rows: list[CT] = []
        for row in source_rows:
            ct = CT(config_relation_uuid=new_cr.uuid, key=row.key, val=row.val)
            self.db.add(ct)
            new_ct_rows.append(ct)

        await self.db.commit()
        await self.db.refresh(new_cr)

        logger.info(
            "Config promoted: %s → %s  proj=%s cmp=%s new_cr=%s",
            payload.from_environment, payload.to_environment,
            payload.proj_id, payload.cmp_id, new_cr.uuid,
        )

        return ConfigReadResponse(
            config_relation_uuid=new_cr.uuid,
            date_created=new_cr.date_created,
            environment=new_cr.environment,
            rows=[CTRowResponse(uuid=ct.uuid, key=ct.key, val=ct.val) for ct in new_ct_rows],
        )

    async def promote_config_by_uuid(self, config_uuid: str, to_environment: str, user_id: str) -> ConfigReadResponse:
        now = datetime.now(timezone.utc)

        # Fetch the specific source snapshot
        src_result = await self.db.execute(
            select(ConfigRelation).where(ConfigRelation.uuid == config_uuid)
        )
        source = src_result.scalar_one_or_none()
        if source is None:
            raise LookupError(f"Config snapshot '{config_uuid}' not found")
        if source.approval_status != "approved":
            raise ValueError(
                f"Cannot promote snapshot with status '{source.approval_status}'"
            )

        # Fetch its CT rows
        ct_result = await self.db.execute(
            select(CT).where(CT.config_relation_uuid == source.uuid)
        )
        source_rows = list(ct_result.scalars().all())

        # Soft-delete previous latest in target environment
        await self.db.execute(
            update(ConfigRelation)
            .where(
                ConfigRelation.proj_id == source.proj_id,
                ConfigRelation.cmp_id == source.cmp_id,
                ConfigRelation.environment == to_environment,
                ConfigRelation.latest == True,  # noqa: E712
            )
            .values(latest=False, date_deleted=now)
        )

        # New config_relation for target environment — auto-approved (source was already vetted)
        new_cr = ConfigRelation(
            proj_id=source.proj_id,
            cmp_id=source.cmp_id,
            environment=to_environment,
            template_version_uuid=source.template_version_uuid,
            latest=True,
            approval_status="approved",
            approved_by=user_id,
            approved_at=now,
            promoted_from_uuid=source.uuid,
        )
        self.db.add(new_cr)
        await self.db.flush()

        self.db.add(ConfigRelationUser(config_relation_uuid=new_cr.uuid, user_id=user_id))

        # Copy CT rows — GT rows are keyed by gid so they remain valid without re-inserting
        new_ct_rows: list[CT] = []
        for row in source_rows:
            ct = CT(config_relation_uuid=new_cr.uuid, key=row.key, val=row.val)
            self.db.add(ct)
            new_ct_rows.append(ct)

        await self.db.commit()
        await self.db.refresh(new_cr)

        logger.info(
            "Config promoted by uuid: %s → %s  proj=%s cmp=%s new_cr=%s",
            source.environment, to_environment,
            source.proj_id, source.cmp_id, new_cr.uuid,
        )

        return ConfigReadResponse(
            config_relation_uuid=new_cr.uuid,
            date_created=new_cr.date_created,
            environment=new_cr.environment,
            rows=[CTRowResponse(uuid=ct.uuid, key=ct.key, val=ct.val) for ct in new_ct_rows],
        )

    async def get_companies_with_config(self, proj_id: str) -> list[str]:
        result = await self.db.execute(
            select(ConfigRelation.cmp_id)
            .where(ConfigRelation.proj_id == proj_id)
            .distinct()
            .order_by(ConfigRelation.cmp_id)
        )
        return list(result.scalars().all())

    async def get_history(self, proj_id: str, cmp_id: str, environment: str) -> list[ConfigHistoryItem]:
        # Fetch all config_relations for this proj+cmp+env with user and entry count
        cr_result = await self.db.execute(
            select(ConfigRelation)
            .where(
                ConfigRelation.proj_id == proj_id,
                ConfigRelation.cmp_id == cmp_id,
                ConfigRelation.environment == environment,
            )
            .order_by(ConfigRelation.date_created.desc())
        )
        relations = list(cr_result.scalars().all())

        items: list[ConfigHistoryItem] = []
        for cr in relations:
            ct_count = await self.db.scalar(
                select(func.count(CT.uuid)).where(CT.config_relation_uuid == cr.uuid)
            )
            user_result = await self.db.execute(
                select(ConfigRelationUser.user_id)
                .where(ConfigRelationUser.config_relation_uuid == cr.uuid)
                .limit(1)
            )
            created_by = user_result.scalar_one_or_none()

            # Resolve template version number if linked
            tmpl_version_number: int | None = None
            if cr.template_version_uuid:
                tv_result = await self.db.execute(
                    select(ProjectTemplateVersion.version_number)
                    .where(ProjectTemplateVersion.uuid == cr.template_version_uuid)
                )
                tmpl_version_number = tv_result.scalar_one_or_none()

            items.append(ConfigHistoryItem(
                config_relation_uuid=cr.uuid,
                date_created=cr.date_created,
                date_deleted=cr.date_deleted,
                created_by=created_by,
                entry_count=ct_count or 0,
                is_latest=cr.latest,
                environment=cr.environment,
                template_version_uuid=cr.template_version_uuid,
                template_version_number=tmpl_version_number,
                approval_status=cr.approval_status,
                approved_by=cr.approved_by,
                approved_at=cr.approved_at,
                rejection_reason=cr.rejection_reason,
                change_description=cr.change_description,
                promoted_from_uuid=cr.promoted_from_uuid,
                name=cr.name,
                proj_id=cr.proj_id,
                cmp_id=cr.cmp_id,
            ))
        return items

    async def get_config_by_uuid(self, uuid: str) -> ConfigReadResponse | None:
        result = await self.db.execute(
            select(ConfigRelation).where(ConfigRelation.uuid == uuid)
        )
        cr = result.scalar_one_or_none()
        if cr is None:
            return None
        ct_result = await self.db.execute(
            select(CT).where(CT.config_relation_uuid == cr.uuid)
        )
        ct_rows = list(ct_result.scalars().all())
        user_result = await self.db.execute(
            select(ConfigRelationUser.user_id)
            .where(ConfigRelationUser.config_relation_uuid == cr.uuid)
            .limit(1)
        )
        created_by = user_result.scalar_one_or_none()
        return ConfigReadResponse(
            config_relation_uuid=cr.uuid,
            date_created=cr.date_created,
            environment=cr.environment,
            rows=[CTRowResponse(uuid=ct.uuid, key=ct.key, val=ct.val) for ct in ct_rows],
            approval_status=cr.approval_status,
            approved_by=cr.approved_by,
            approved_at=cr.approved_at,
            rejection_reason=cr.rejection_reason,
            created_by=created_by,
            is_latest=cr.latest,
            change_description=cr.change_description,
            promoted_from_uuid=cr.promoted_from_uuid,
            proj_id=cr.proj_id,
            cmp_id=cr.cmp_id,
            name=cr.name,
        )


    async def _search_candidate_configs(
        self,
        snapshot: ConfigReadResponse,
        source_entries: list[dict[str, str | bool]],
        token: str,
    ) -> list[ConfigHistoryItem]:
        candidate_ids: set[str] = set()
        candidate_counts: dict[str, int] = defaultdict(int)
        cmp_scope = snapshot.cmp_id or ""

        for entry in source_entries:
            key_alias = str(entry["key_alias"])
            value_display = str(entry["value_display"])

            if key_alias:
                try:
                    hits = await self._ssot_get_json("/api/v1/search", token, params={"q": key_alias, "cmpid": cmp_scope})
                except httpx.HTTPError as exc:
                    logger.warning("SSOT key search failed for %s: %s", key_alias, exc)
                    hits = []

                for hit in hits[:5]:
                    truth_id = hit.get("truth")
                    if not truth_id:
                        continue
                    try:
                        truth_node = await self._ssot_get_json(f"/api/v1/truth/{truth_id}", token)
                    except httpx.HTTPError:
                        continue
                    key_uuid = truth_node.get("latestName")
                    if not key_uuid:
                        continue
                    try:
                        configs = await self.search_configs(
                            q=None,
                            key_uuids=[str(key_uuid)],
                            proj_id=snapshot.proj_id,
                            cmp_id=snapshot.cmp_id,
                            environment=None,
                            skip=0,
                            limit=10,
                        )
                    except Exception:
                        configs = []
                    for config in configs:
                        if config.config_relation_uuid == snapshot.config_relation_uuid:
                            continue
                        candidate_ids.add(config.config_relation_uuid)
                        candidate_counts[config.config_relation_uuid] += 1

            if value_display and not bool(entry.get("is_group")):
                try:
                    hits = await self._ssot_get_json(
                        "/api/v1/search/value",
                        token,
                        params={"q": value_display, "name": key_alias, "cmpid": cmp_scope},
                    )
                except httpx.HTTPError as exc:
                    logger.warning("SSOT value search failed for %s: %s", key_alias, exc)
                    hits = []

                for hit in hits[:5]:
                    truth_id = hit.get("truth")
                    if not truth_id:
                        continue
                    try:
                        truth_node = await self._ssot_get_json(f"/api/v1/truth/{truth_id}", token)
                    except httpx.HTTPError:
                        continue
                    key_uuid = truth_node.get("latestName")
                    if not key_uuid:
                        continue
                    try:
                        configs = await self.search_configs(
                            q=None,
                            key_uuids=[str(key_uuid)],
                            proj_id=snapshot.proj_id,
                            cmp_id=snapshot.cmp_id,
                            environment=None,
                            skip=0,
                            limit=10,
                        )
                    except Exception:
                        configs = []
                    for config in configs:
                        if config.config_relation_uuid == snapshot.config_relation_uuid:
                            continue
                        candidate_ids.add(config.config_relation_uuid)
                        candidate_counts[config.config_relation_uuid] += 1

        if snapshot.proj_id or snapshot.cmp_id:
            baseline = await self.search_configs(
                q=None,
                key_uuids=None,
                proj_id=snapshot.proj_id,
                cmp_id=snapshot.cmp_id,
                environment=None,
                skip=0,
                limit=20,
            )
            for config in baseline:
                if config.config_relation_uuid != snapshot.config_relation_uuid:
                    candidate_ids.add(config.config_relation_uuid)
                    candidate_counts[config.config_relation_uuid] += 1

        if not candidate_ids:
            return []

        scored_candidates = sorted(candidate_ids, key=lambda cid: (candidate_counts[cid], cid), reverse=True)
        result: list[ConfigHistoryItem] = []
        for candidate_id in scored_candidates[:20]:
            candidate = await self.get_config_by_uuid(candidate_id)
            if candidate is None:
                continue
            result.append(
                ConfigHistoryItem(
                    config_relation_uuid=candidate.config_relation_uuid,
                    date_created=candidate.date_created,
                    date_deleted=None,
                    created_by=candidate.created_by,
                    entry_count=len(candidate.rows),
                    is_latest=bool(candidate.is_latest),
                    environment=candidate.environment,
                    template_version_uuid=None,
                    template_version_number=None,
                    approval_status=candidate.approval_status or "pending",
                    approved_by=candidate.approved_by,
                    approved_at=candidate.approved_at,
                    rejection_reason=candidate.rejection_reason,
                    change_description=candidate.change_description,
                    promoted_from_uuid=candidate.promoted_from_uuid,
                    name=candidate.name,
                    proj_id=candidate.proj_id,
                    cmp_id=candidate.cmp_id,
                )
            )
        return result

    async def review_similarity_report(self, config_uuid: str, token: str, limit: int = 5, threshold: float = 0.45) -> ReviewSimilarityReport:
        snapshot = await self.get_config_by_uuid(config_uuid)
        if snapshot is None:
            raise LookupError(f"Config snapshot '{config_uuid}' not found")

        node_cache: dict[str, dict | None] = {}
        source_entries = await self._flatten_config_rows(snapshot.rows, token, node_cache)
        source_models = [
            ReviewSimilaritySourceEntry(
                path=str(entry["path"]),
                key_uuid=str(entry["key_uuid"]),
                key_alias=str(entry["key_alias"]),
                value_ref=str(entry["value_ref"]),
                value_display=str(entry["value_display"]),
                is_group=bool(entry["is_group"]),
            )
            for entry in source_entries
        ]

        candidate_histories = await self._search_candidate_configs(snapshot, source_entries, token)

        candidates: list[ReviewSimilarityCandidate] = []
        for candidate_history in candidate_histories:
            candidate_snapshot = await self.get_config_by_uuid(candidate_history.config_relation_uuid)
            if candidate_snapshot is None:
                continue

            candidate_cache: dict[str, dict | None] = {}
            candidate_entries = await self._flatten_config_rows(candidate_snapshot.rows, token, candidate_cache)
            matched_entries: list[ReviewSimilarityEntryMatch] = []

            for source_entry in source_entries:
                best_match: dict[str, str | float] | None = None
                best_score = 0.0
                for candidate_entry in candidate_entries:
                    key_score = self._text_similarity(str(source_entry["key_alias"]), str(candidate_entry["key_alias"]))
                    value_score = self._text_similarity(str(source_entry["value_display"]), str(candidate_entry["value_display"]))
                    path_score = self._text_similarity(str(source_entry["path"]), str(candidate_entry["path"]))
                    score = (key_score * 0.5) + (value_score * 0.4) + (path_score * 0.1)
                    if score > best_score:
                        best_score = score
                        best_match = {
                            "candidate_path": str(candidate_entry["path"]),
                            "candidate_key_alias": str(candidate_entry["key_alias"]),
                            "candidate_value_display": str(candidate_entry["value_display"]),
                            "candidate_value_ref": str(candidate_entry["value_ref"]),
                            "match_kind": "key" if key_score >= value_score else "value",
                            "score": score,
                            "key_score": key_score,
                            "value_score": value_score,
                        }

                if not best_match:
                    continue

                source_key = self._normalize_text(str(source_entry["key_alias"]))
                candidate_key = self._normalize_text(str(best_match["candidate_key_alias"]))
                source_value = self._normalize_text(str(source_entry["value_display"]))
                candidate_value = self._normalize_text(str(best_match["candidate_value_display"]))
                same_key = source_key == candidate_key
                same_value = source_value != "" and source_value == candidate_value and not same_key
                similar_key = not same_key and self._text_similarity(str(source_entry["key_alias"]), str(best_match["candidate_key_alias"])) >= 0.7

                display_state = "hidden"
                display_reason = "different_key_different_value"
                if same_key:
                    display_reason = "same_key"
                elif same_value:
                    display_state = "shown"
                    display_reason = "same_value"
                elif similar_key:
                    display_state = "shown"
                    display_reason = "similar_key"

                if display_state == "hidden" and best_score < threshold:
                    continue

                matched_entries.append(
                    ReviewSimilarityEntryMatch(
                        source_path=str(source_entry["path"]),
                        source_key_alias=str(source_entry["key_alias"]),
                        source_value_display=str(source_entry["value_display"]),
                        source_value_ref=str(source_entry["value_ref"]),
                        candidate_path=str(best_match["candidate_path"]),
                        candidate_key_alias=str(best_match["candidate_key_alias"]),
                        candidate_value_display=str(best_match["candidate_value_display"]),
                        candidate_value_ref=str(best_match["candidate_value_ref"]),
                        match_kind=str(best_match["match_kind"]),
                        score=float(best_match["score"]),
                        display_state=display_state,
                        display_reason=display_reason,
                    )
                )

            if not matched_entries:
                continue

            avg_score = sum(match.score for match in matched_entries) / max(len(source_entries), 1)
            candidates.append(
                ReviewSimilarityCandidate(
                    config_relation_uuid=candidate_snapshot.config_relation_uuid,
                    date_created=candidate_snapshot.date_created,
                    environment=candidate_snapshot.environment,
                    approval_status=candidate_snapshot.approval_status or "pending",
                    score=round(avg_score, 4),
                    name=candidate_snapshot.name,
                    proj_id=candidate_snapshot.proj_id,
                    cmp_id=candidate_snapshot.cmp_id,
                    matched_entries=sorted(matched_entries, key=lambda item: item.score, reverse=True)[:limit],
                )
            )

        candidates.sort(key=lambda item: (item.score, item.date_created), reverse=True)

        return ReviewSimilarityReport(
            config_relation_uuid=snapshot.config_relation_uuid,
            date_created=snapshot.date_created,
            environment=snapshot.environment,
            approval_status=snapshot.approval_status or "pending",
            created_by=snapshot.created_by,
            name=snapshot.name,
            proj_id=snapshot.proj_id,
            cmp_id=snapshot.cmp_id,
            source_entry_count=len(source_models),
            candidate_count=len(candidates),
            source_entries=source_models,
            candidates=candidates[:limit],
        )
    async def get_config(self, proj_id: str, cmp_id: str, environment: str = "production") -> ConfigReadResponse | None:
        result = await self.db.execute(
            select(ConfigRelation).where(
                ConfigRelation.proj_id == proj_id,
                ConfigRelation.cmp_id == cmp_id,
                ConfigRelation.environment == environment,
                ConfigRelation.latest == True,  # noqa: E712
            )
        )
        cr = result.scalar_one_or_none()
        if cr is None:
            return None

        ct_result = await self.db.execute(
            select(CT).where(CT.config_relation_uuid == cr.uuid)
        )
        ct_rows = list(ct_result.scalars().all())

        return ConfigReadResponse(
            config_relation_uuid=cr.uuid,
            date_created=cr.date_created,
            environment=cr.environment,
            rows=[CTRowResponse(uuid=ct.uuid, key=ct.key, val=ct.val) for ct in ct_rows],
        )

    async def approve_config(self, config_uuid: str, approver_id: str) -> ConfigApprovalResponse:
        now = datetime.now(timezone.utc)

        result = await self.db.execute(select(ConfigRelation).where(ConfigRelation.uuid == config_uuid))
        cr = result.scalar_one_or_none()
        if cr is None:
            raise LookupError(f"Config snapshot '{config_uuid}' not found")
        if cr.approval_status != "pending":
            raise ValueError(f"Config is already '{cr.approval_status}', cannot approve")

        user_result = await self.db.execute(
            select(ConfigRelationUser.user_id)
            .where(ConfigRelationUser.config_relation_uuid == config_uuid)
            .limit(1)
        )
        submitter = user_result.scalar_one_or_none()
        if submitter == approver_id:
            raise PermissionError("Cannot approve your own config submission")

        # Soft-delete current latest in same scope
        await self.db.execute(
            update(ConfigRelation)
            .where(
                ConfigRelation.proj_id == cr.proj_id,
                ConfigRelation.cmp_id == cr.cmp_id,
                ConfigRelation.environment == cr.environment,
                ConfigRelation.latest == True,  # noqa: E712
            )
            .values(latest=False, date_deleted=now)
        )

        cr.approval_status = "approved"
        cr.approved_by = approver_id
        cr.approved_at = now
        cr.latest = True
        await self.db.commit()
        await self.db.refresh(cr)

        logger.info("Config approved: %s by %s", config_uuid, approver_id)
        return ConfigApprovalResponse(
            config_relation_uuid=cr.uuid,
            approval_status=cr.approval_status,
            approved_by=cr.approved_by,
            approved_at=cr.approved_at,
            rejection_reason=cr.rejection_reason,
        )

    async def get_children(self, uuid: str) -> list[ConfigHistoryItem]:
        cr_result = await self.db.execute(
            select(ConfigRelation)
            .where(ConfigRelation.promoted_from_uuid == uuid)
            .order_by(ConfigRelation.date_created.asc())
        )
        relations = list(cr_result.scalars().all())

        items: list[ConfigHistoryItem] = []
        for cr in relations:
            ct_count = await self.db.scalar(
                select(func.count(CT.uuid)).where(CT.config_relation_uuid == cr.uuid)
            )
            user_result = await self.db.execute(
                select(ConfigRelationUser.user_id)
                .where(ConfigRelationUser.config_relation_uuid == cr.uuid)
                .limit(1)
            )
            created_by = user_result.scalar_one_or_none()
            items.append(ConfigHistoryItem(
                config_relation_uuid=cr.uuid,
                date_created=cr.date_created,
                date_deleted=cr.date_deleted,
                created_by=created_by,
                entry_count=ct_count or 0,
                is_latest=cr.latest,
                environment=cr.environment,
                template_version_uuid=cr.template_version_uuid,
                template_version_number=None,
                approval_status=cr.approval_status,
                approved_by=cr.approved_by,
                approved_at=cr.approved_at,
                rejection_reason=cr.rejection_reason,
                change_description=cr.change_description,
                promoted_from_uuid=cr.promoted_from_uuid,
            ))
        return items

    async def reject_config(self, config_uuid: str, rejector_id: str, reason: str | None) -> ConfigApprovalResponse:
        result = await self.db.execute(select(ConfigRelation).where(ConfigRelation.uuid == config_uuid))
        cr = result.scalar_one_or_none()
        if cr is None:
            raise LookupError(f"Config snapshot '{config_uuid}' not found")
        if cr.approval_status != "pending":
            raise ValueError(f"Config is already '{cr.approval_status}', cannot reject")

        user_result = await self.db.execute(
            select(ConfigRelationUser.user_id)
            .where(ConfigRelationUser.config_relation_uuid == config_uuid)
            .limit(1)
        )
        submitter = user_result.scalar_one_or_none()
        if submitter == rejector_id:
            raise PermissionError("Cannot reject your own config submission")

        cr.approval_status = "rejected"
        cr.approved_by = rejector_id
        cr.rejection_reason = reason
        await self.db.commit()
        await self.db.refresh(cr)

        logger.info("Config rejected: %s by %s", config_uuid, rejector_id)
        return ConfigApprovalResponse(
            config_relation_uuid=cr.uuid,
            approval_status=cr.approval_status,
            approved_by=cr.approved_by,
            approved_at=cr.approved_at,
            rejection_reason=cr.rejection_reason,
        )

    async def update_pending_config(self, config_uuid: str, entries: list[ConfigEntrySchema], editor_id: str) -> ConfigReadResponse:
        result = await self.db.execute(select(ConfigRelation).where(ConfigRelation.uuid == config_uuid))
        cr = result.scalar_one_or_none()
        if cr is None:
            raise LookupError(f"Config snapshot '{config_uuid}' not found")
        if cr.approval_status != "pending":
            raise ValueError(f"Only pending snapshots can be edited (status: '{cr.approval_status}')")

        user_result = await self.db.execute(
            select(ConfigRelationUser.user_id)
            .where(ConfigRelationUser.config_relation_uuid == config_uuid)
            .limit(1)
        )
        submitter = user_result.scalar_one_or_none()
        if submitter == editor_id:
            raise PermissionError("Cannot edit a snapshot you submitted")

        await self.db.execute(delete(CT).where(CT.config_relation_uuid == config_uuid))

        ct_rows: list[CT] = []
        for entry in entries:
            ct = CT(config_relation_uuid=cr.uuid, key=entry.key, val=entry.val)
            self.db.add(ct)
            ct_rows.append(ct)
            if entry.group_entries:
                self._insert_gt_rows(entry.group_entries)

        await self.db.commit()
        await self.db.refresh(cr)

        logger.info("Pending config updated by reviewer: %s by %s", config_uuid, editor_id)
        return ConfigReadResponse(
            config_relation_uuid=cr.uuid,
            date_created=cr.date_created,
            environment=cr.environment,
            rows=[CTRowResponse(uuid=ct.uuid, key=ct.key, val=ct.val) for ct in ct_rows],
            approval_status=cr.approval_status,
            name=cr.name,
        )

    async def search_configs(
        self,
        q: str | None,
        key_uuids: list[str] | None,
        proj_id: str | None,
        cmp_id: str | None,
        environment: str | None,
        approval_status: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[ConfigHistoryItem]:
        stmt = select(ConfigRelation)

        filters = []
        if q:
            pattern = f"%{q}%"
            filters.append(or_(
                ConfigRelation.name.ilike(pattern),
                ConfigRelation.proj_id.ilike(pattern),
                ConfigRelation.cmp_id.ilike(pattern),
            ))
        if proj_id:
            filters.append(ConfigRelation.proj_id == proj_id)
        if cmp_id:
            filters.append(ConfigRelation.cmp_id == cmp_id)
        if environment:
            filters.append(ConfigRelation.environment == environment)
        if approval_status:
            filters.append(ConfigRelation.approval_status == approval_status)

        if key_uuids:
            # subquery: config_relation_uuids that have at least one matching CT key
            sub = select(CT.config_relation_uuid).where(CT.key.in_(key_uuids)).distinct()
            filters.append(ConfigRelation.uuid.in_(sub))

        if filters:
            stmt = stmt.where(*filters)

        stmt = stmt.order_by(ConfigRelation.date_created.desc()).offset(skip).limit(limit)
        cr_result = await self.db.execute(stmt)
        relations = list(cr_result.scalars().all())

        items: list[ConfigHistoryItem] = []
        for cr in relations:
            ct_count = await self.db.scalar(
                select(func.count(CT.uuid)).where(CT.config_relation_uuid == cr.uuid)
            )
            user_result = await self.db.execute(
                select(ConfigRelationUser.user_id)
                .where(ConfigRelationUser.config_relation_uuid == cr.uuid)
                .limit(1)
            )
            created_by = user_result.scalar_one_or_none()

            tmpl_version_number: int | None = None
            if cr.template_version_uuid:
                tv_result = await self.db.execute(
                    select(ProjectTemplateVersion.version_number)
                    .where(ProjectTemplateVersion.uuid == cr.template_version_uuid)
                )
                tmpl_version_number = tv_result.scalar_one_or_none()

            items.append(ConfigHistoryItem(
                config_relation_uuid=cr.uuid,
                date_created=cr.date_created,
                date_deleted=cr.date_deleted,
                created_by=created_by,
                entry_count=ct_count or 0,
                is_latest=cr.latest,
                environment=cr.environment,
                template_version_uuid=cr.template_version_uuid,
                template_version_number=tmpl_version_number,
                approval_status=cr.approval_status,
                approved_by=cr.approved_by,
                approved_at=cr.approved_at,
                rejection_reason=cr.rejection_reason,
                change_description=cr.change_description,
                promoted_from_uuid=cr.promoted_from_uuid,
                name=cr.name,
                proj_id=cr.proj_id,
                cmp_id=cr.cmp_id,
            ))
        return items

    async def get_pending_reviews(self, skip: int = 0, limit: int = 20) -> list[ConfigHistoryItem]:
        return await self.search_configs(
            q=None,
            key_uuids=None,
            proj_id=None,
            cmp_id=None,
            environment=None,
            approval_status="pending",
            skip=skip,
            limit=limit,
        )
