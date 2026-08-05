from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Law, LawVersion, LegalArticle
from app.services.embeddings import embed

DEFAULT_EFFECTIVE_FROM = date(1900, 1, 1)
CIVIL_CODE_EFFECTIVE_FROM = date(2021, 1, 1)
CONTRACT_LAW_EFFECTIVE_FROM = date(1999, 10, 1)
CONTRACT_LAW_EFFECTIVE_TO = CIVIL_CODE_EFFECTIVE_FROM


def _default_version_metadata(law_name: str) -> tuple[str, date, str]:
    if law_name == "中华人民共和国民法典":
        return "2020年通过（2021年施行）", CIVIL_CODE_EFFECTIVE_FROM, "国家法律法规数据库现行文本"
    return "知识库现行版本", DEFAULT_EFFECTIVE_FROM, "项目知识库现行版本"


def _get_or_create_law(db: Session, name: str) -> Law:
    law = db.scalar(select(Law).where(Law.name == name))
    if law is None:
        law = Law(name=name)
        db.add(law)
        db.flush()
    return law


def _get_or_create_current_version(db: Session, law: Law) -> LawVersion:
    version = db.scalar(
        select(LawVersion)
        .where(
            LawVersion.law_id == law.id,
            LawVersion.effective_to.is_(None),
        )
        .order_by(LawVersion.effective_from.desc())
    )
    if version is not None:
        return version
    label, effective_from, source = _default_version_metadata(law.name)
    version = LawVersion(
        law_id=law.id,
        version_label=label,
        effective_from=effective_from,
        effective_to=None,
        status="effective",
        source=source,
    )
    db.add(version)
    db.flush()
    return version


def attach_article_to_current_version(db: Session, article: LegalArticle) -> LawVersion:
    """Bind a newly imported legacy article to its law's current version."""
    if article.law_name == "中华人民共和国合同法":
        historical, _ = _ensure_contract_transition_demo(db)
        article.law_version_id = historical.id
        return historical
    law = _get_or_create_law(db, article.law_name)
    version = _get_or_create_current_version(db, law)
    article.law_version_id = version.id
    return version


def _ensure_contract_transition_demo(db: Session) -> tuple[LawVersion, LawVersion]:
    contract_law = _get_or_create_law(db, "中华人民共和国合同法")
    historical = db.scalar(
        select(LawVersion).where(
            LawVersion.law_id == contract_law.id,
            LawVersion.version_label == "1999年施行版本",
        )
    )
    if historical is None:
        historical = LawVersion(
            law_id=contract_law.id,
            version_label="1999年施行版本",
            effective_from=CONTRACT_LAW_EFFECTIVE_FROM,
            effective_to=CONTRACT_LAW_EFFECTIVE_TO,
            status="repealed",
            source="国家法律法规数据库历史文本；教学节选",
        )
        db.add(historical)
        db.flush()

    civil_code = _get_or_create_law(db, "中华人民共和国民法典")
    current = _get_or_create_current_version(db, civil_code)
    if current.supersedes_version_id != historical.id:
        current.supersedes_version_id = historical.id

    article = db.scalar(
        select(LegalArticle).where(
            LegalArticle.law_name == "中华人民共和国合同法",
            LegalArticle.article_number == "第九十四条",
        )
    )
    if article is None:
        content = (
            "有下列情形之一的，当事人可以解除合同：因不可抗力致使不能实现合同目的；"
            "在履行期限届满之前，当事人一方明确表示或者以自己的行为表明不履行主要债务；"
            "当事人一方迟延履行主要债务，经催告后在合理期限内仍未履行；"
            "当事人一方迟延履行债务或者有其他违约行为致使不能实现合同目的；"
            "法律规定的其他情形。"
        )
        article = LegalArticle(
            law_name="中华人民共和国合同法",
            article_number="第九十四条",
            content=content,
            source="国家法律法规数据库历史文本；教学节选",
            embedding=embed(content),
            law_version_id=historical.id,
        )
        db.add(article)
    else:
        article.law_version_id = historical.id
    return historical, current


def ensure_law_version_data(db: Session) -> int:
    """Backfill version metadata and add one reproducible before/after transition."""
    articles = db.scalars(select(LegalArticle)).all()
    current_versions: dict[str, LawVersion] = {}
    for law_name in sorted({article.law_name for article in articles}):
        # The Contract Law only exists as a historical demo version. Do not
        # manufacture a second "current" version for it on repeated startups.
        if law_name == "中华人民共和国合同法":
            continue
        law = _get_or_create_law(db, law_name)
        current_versions[law_name] = _get_or_create_current_version(db, law)

    historical, _ = _ensure_contract_transition_demo(db)
    updated = 0
    for article in articles:
        if article.law_version_id is not None:
            continue
        if article.law_name == "中华人民共和国合同法" and article.article_number == "第九十四条":
            article.law_version_id = historical.id
        else:
            article.law_version_id = current_versions[article.law_name].id
        updated += 1
    db.commit()
    return updated
