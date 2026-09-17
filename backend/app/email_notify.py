"""Job-completion email notifications over plain SMTP.

Attaches the generated video directly rather than emailing a download link:
Render's free tier has no persistent disk, so a link can 404 once the
service restarts or redeploys, while an attachment survives independently
of the server. Falls back to a link (when PUBLIC_BASE_URL is configured)
only for videos too large to attach.
"""
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from . import config
from .models import Job, JobStatus

# Stay well under common provider/SMTP relay attachment caps (Gmail's is ~25MB).
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024


def is_configured() -> bool:
    return bool(config.SMTP_HOST and config.SMTP_USER and config.SMTP_PASSWORD)


def _build_message(job: Job, to_email: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = config.SMTP_FROM
    msg["To"] = to_email

    if job.status == JobStatus.DONE:
        msg["Subject"] = f"[동영상 생성기] 작업 완료 ({job.id})"
        output = Path(job.output_path) if job.output_path else None
        attach = bool(output and output.exists() and output.stat().st_size <= MAX_ATTACHMENT_BYTES)

        body = "요청하신 동영상 생성이 완료됐습니다.\n\n"
        if attach:
            body += "생성된 영상을 첨부했습니다."
        elif config.PUBLIC_BASE_URL:
            body += (
                "영상 용량이 커서 첨부하지 못했습니다. 아래 링크에서 다운로드하세요\n"
                "(서버가 재시작되면 파일이 사라질 수 있으니 되도록 빨리 받아주세요):\n"
                f"{config.PUBLIC_BASE_URL}/api/jobs/{job.id}/download"
            )
        else:
            body += "영상 용량이 커서 첨부하지 못했고, 다운로드 링크를 만들 PUBLIC_BASE_URL도 설정되어 있지 않습니다."
        msg.set_content(body)

        if attach:
            msg.add_attachment(
                output.read_bytes(), maintype="video", subtype="mp4", filename=f"{job.id}.mp4"
            )
    else:
        msg["Subject"] = f"[동영상 생성기] 작업 실패 ({job.id})"
        msg.set_content(f"동영상 생성에 실패했습니다.\n\n오류: {job.error or '(알 수 없음)'}")

    return msg


def send_job_notification(job: Job, to_email: str) -> None:
    if not is_configured():
        raise RuntimeError(
            "SMTP is not configured (set SMTP_HOST/SMTP_USER/SMTP_PASSWORD env vars)"
        )

    msg = _build_message(job, to_email)
    context = ssl.create_default_context()
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)
