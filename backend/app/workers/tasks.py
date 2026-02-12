from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models import Candidate, Scan, ScanFile, ScanStatus, ScanType
from app.services.candidate_generation import discover_candidates
from app.services.extraction import extract_text
from app.services.sentence_transformer_pipeline import run_sentence_transformer_scan
from app.services.storage import write_artifact
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.process_scan")
def process_scan(
    scan_id: str,
    exchange_access_token: str | None = None,
    exchange_organization: str | None = None,
) -> dict:
    with SessionLocal() as db:
        scan = db.get(Scan, UUID(scan_id))
        if scan is None:
            return {"scan_id": scan_id, "status": "MISSING"}

        try:
            started = datetime.now(tz=timezone.utc)
            scan.status = ScanStatus.EXTRACTING
            db.commit()

            files = db.scalars(select(ScanFile).where(ScanFile.scan_id == scan.scan_id)).all()
            total_files = len(files)
            extracted_text_chunks: list[str] = []
            extracted_text_by_file: list[tuple[ScanFile, str]] = []
            extraction_info_by_file: dict[str, dict[str, object]] = {}
            ocr_confidences: list[float] = []
            scan_metadata = scan.metadata_json or {}
            user_principal_name = scan_metadata.get("user_principal_name")
            preserve_case = bool(scan_metadata.get("preserve_case", False))
            force_ocr = bool(scan_metadata.get("force_ocr", False))
            sit_category = scan_metadata.get("sit_category")

            def update_progress(
                *,
                phase: str,
                progress_pct: float,
                current_file_name: str | None = None,
                files_completed: int | None = None,
            ) -> None:
                metadata = dict(scan.metadata_json or {})
                metadata["processing_phase"] = phase
                metadata["processing_progress_pct"] = round(max(0.0, min(100.0, progress_pct)), 2)
                metadata["files_total"] = total_files
                if files_completed is not None:
                    metadata["files_completed"] = files_completed
                if current_file_name:
                    metadata["current_file_name"] = current_file_name
                scan.metadata_json = metadata
                db.commit()

            update_progress(phase="extracting", progress_pct=0, files_completed=0)

            for idx, item in enumerate(files, start=1):
                update_progress(
                    phase="extracting",
                    progress_pct=((idx - 1) / total_files * 70) if total_files else 0,
                    current_file_name=item.file_name,
                    files_completed=idx - 1,
                )
                result = extract_text(item.blob_path or "", item.file_type, force_ocr=force_ocr)
                artifact_path = write_artifact(str(scan.scan_id), f"{item.file_id}.txt", result.text)

                item.extracted_text_blob_path = artifact_path
                item.extraction_method = result.method
                item.ocr_confidence = result.ocr_confidence
                item.page_count = result.page_count
                metadata_ocr = result.metadata.get("ocr_performed")
                ocr_performed = bool(metadata_ocr) or (result.method or "").upper() == "OCR"
                extraction_info_by_file[str(item.file_id)] = {
                    "extraction_module": result.metadata.get("module", "unknown"),
                    "ocr_performed": ocr_performed,
                }

                if result.text:
                    extracted_text_chunks.append(result.text)
                    extracted_text_by_file.append((item, result.text))
                if result.ocr_confidence is not None:
                    ocr_confidences.append(result.ocr_confidence)

                update_progress(
                    phase="extracting",
                    progress_pct=(idx / total_files * 70) if total_files else 70,
                    current_file_name=item.file_name,
                    files_completed=idx,
                )

            extraction_finished = datetime.now(tz=timezone.utc)
            scan.status = ScanStatus.EXTRACTED
            scan.extraction_duration_sec = (extraction_finished - started).total_seconds()

            combined_text = "\n\n".join(extracted_text_chunks)
            scan.extracted_text_length = len(combined_text)

            scan.status = ScanStatus.ANALYZING
            db.commit()
            update_progress(phase="analyzing", progress_pct=70, files_completed=total_files)

            if scan.scan_type == ScanType.SENTENCE_TRANSFORMER:
                if not exchange_access_token:
                    raise RuntimeError("exchange_access_token is required for sentence_transformer scans")

                candidates = []
                for idx, item in enumerate(files, start=1):
                    progress = 70 + ((idx - 1) / total_files * 30) if total_files else 85
                    update_progress(
                        phase="analyzing",
                        progress_pct=progress,
                        current_file_name=item.file_name,
                        files_completed=total_files,
                    )
                    phrases = run_sentence_transformer_scan(
                        file_path=item.blob_path or "",
                        user_principal_name=user_principal_name,
                        exchange_access_token=exchange_access_token,
                        organization=exchange_organization,
                        preserve_case=preserve_case,
                    )
                    for phrase in phrases:
                        candidates.append(
                            {
                                "candidate_type": "KEYWORD",
                                "element_type_hint": "KEYWORD_LIST",
                                "value": phrase.phrase,
                                "pattern_template": None,
                                "frequency": 1,
                                "confidence": max(0.0, min(1.0, phrase.score)),
                                "score": round(phrase.score * 100, 4),
                                "metadata": {
                                    "source": "sentence_transformer",
                                    "stream_name": phrase.stream_name,
                                    "file_name": item.file_name,
                                    "sit_category": sit_category,
                                    "extraction_module": extraction_info_by_file.get(str(item.file_id), {}).get("extraction_module", "unknown"),
                                    "ocr_performed": extraction_info_by_file.get(str(item.file_id), {}).get("ocr_performed", False),
                                },
                            }
                        )
                    update_progress(
                        phase="analyzing",
                        progress_pct=70 + (idx / total_files * 30) if total_files else 95,
                        current_file_name=item.file_name,
                        files_completed=total_files,
                    )
            else:
                candidates = []
                for item, file_text in extracted_text_by_file:
                    file_name = item.file_name or (Path(item.blob_path).name if item.blob_path else "Unknown file")
                    discovered = discover_candidates(file_text)
                    for candidate in discovered:
                        candidates.append(
                            {
                                "candidate_type": candidate.candidate_type,
                                "element_type_hint": candidate.element_type_hint,
                                "value": candidate.value,
                                "pattern_template": candidate.pattern_template,
                                "frequency": candidate.frequency,
                                "confidence": candidate.confidence,
                                "score": candidate.score,
                                "metadata": {
                                    **(candidate.metadata or {}),
                                    "file_name": file_name,
                                    "sit_category": sit_category,
                                    "extraction_module": extraction_info_by_file.get(str(item.file_id), {}).get("extraction_module", "unknown"),
                                    "ocr_performed": extraction_info_by_file.get(str(item.file_id), {}).get("ocr_performed", False),
                                },
                                "entropy": candidate.metadata.get("entropy"),
                                "evidence": candidate.evidence,
                            }
                        )
                update_progress(phase="analyzing", progress_pct=95, files_completed=total_files)

            db.execute(delete(Candidate).where(Candidate.scan_id == scan.scan_id))
            for candidate in candidates:
                db.add(
                    Candidate(
                        scan_id=scan.scan_id,
                        candidate_type=candidate["candidate_type"],
                        element_type_hint=candidate["element_type_hint"],
                        value=candidate["value"],
                        pattern_template=candidate["pattern_template"],
                        frequency=candidate["frequency"],
                        document_frequency=1,
                        confidence=candidate["confidence"],
                        entropy=candidate.get("entropy"),
                        score=candidate["score"],
                        evidence=candidate.get("evidence"),
                        metadata_json=candidate["metadata"],
                    )
                )

            finished = datetime.now(tz=timezone.utc)
            scan.status = ScanStatus.COMPLETED
            scan.completed_at = finished
            scan.analysis_duration_sec = (finished - extraction_finished).total_seconds()
            scan.ocr_confidence_avg = sum(ocr_confidences) / len(ocr_confidences) if ocr_confidences else None

            file_types = sorted({item.file_type for item in files if item.file_type})
            scan.metadata_json = {
                **(scan.metadata_json or {}),
                "file_types": file_types,
                "quality_flags": ["high_ocr_confidence"] if (scan.ocr_confidence_avg or 0) >= 0.9 else [],
                "processing_phase": "completed",
                "processing_progress_pct": 100,
                "files_completed": total_files,
            }

            db.commit()

            return {"scan_id": str(scan.scan_id), "status": scan.status, "candidates": len(candidates)}
        except Exception as exc:
            scan.status = ScanStatus.FAILED
            scan.error_message = str(exc)
            scan.completed_at = datetime.now(tz=timezone.utc)
            scan.metadata_json = {
                **(scan.metadata_json or {}),
                "processing_phase": "failed",
                "processing_progress_pct": 100,
            }
            db.commit()
            raise
