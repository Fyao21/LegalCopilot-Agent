import random
import unittest
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.services.case_analyzer import analyze_case
from app.services.document_parser import UnsupportedDocumentError, extract_text
from app.services.embeddings import cosine_similarity, embed
from app.services.knowledge_import import KnowledgeImportError, parse_knowledge_text_file
from app.services.knowledge_normalizer import (
    decode_unstructured_knowledge_file,
    normalize_knowledge_text,
)
from app.services.question_examples import generate_question_examples

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class FakeNormalizerLLM:
    model = "test-normalizer"

    def __init__(self, response: dict[str, object]):
        self.response = response

    def invoke_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
    ) -> SchemaT:
        return schema.model_validate(self.response)


class ServiceTests(unittest.TestCase):
    def test_contract_case_analysis(self) -> None:
        result = analyze_case(
            "原告：张三。被告未按合同交付货物，原告请求赔偿损失。",
            "被告是否构成违约？",
        )
        self.assertEqual(result.case_type, "合同纠纷")
        self.assertIn("张三", result.parties)
        self.assertTrue(result.claims)

    def test_food_poisoning_is_classified_as_food_safety_dispute(self) -> None:
        result = analyze_case("", "食物中毒商家需要负责吗")

        self.assertEqual(result.case_type, "食品安全与消费者权益纠纷")
        self.assertIn("食物中毒商家需要负责吗", result.key_facts)
        self.assertIn("食物中毒商家需要负责吗", result.dispute_focuses)

    def test_question_examples_are_unique_and_support_category_filter(self) -> None:
        examples = generate_question_examples(
            10,
            "食品安全",
            rng=random.Random(20260726),
        )

        self.assertEqual(len(examples), 10)
        self.assertEqual(len({item["example_id"] for item in examples}), 10)
        self.assertEqual(len({item["question"] for item in examples}), 10)
        self.assertTrue(all(item["category"] == "食品安全" for item in examples))

    def test_detailed_question_examples_include_background_and_evidence(self) -> None:
        example = generate_question_examples(
            1,
            "食品安全",
            "detailed",
            rng=random.Random(20260726),
        )[0]

        self.assertEqual(example["detail_level"], "detailed")
        self.assertGreater(len(example["question"]), 180)
        self.assertIn("保留", example["question"])
        self.assertIn("想了解", example["question"])
        self.assertIn("商家", example["question"])

    def test_text_document(self) -> None:
        self.assertEqual(extract_text("case.txt", "合同纠纷".encode()), "合同纠纷")

    def test_unsupported_document(self) -> None:
        with self.assertRaises(UnsupportedDocumentError):
            extract_text("case.exe", b"invalid")

    def test_embedding_similarity(self) -> None:
        query = embed("合同违约赔偿")
        relevant = embed("合同违约责任赔偿损失")
        unrelated = embed("劳动工资支付")
        self.assertGreater(cosine_similarity(query, relevant), cosine_similarity(query, unrelated))

    def test_cosine_similarity_normalizes_external_vectors(self) -> None:
        self.assertAlmostEqual(cosine_similarity([2.0, 0.0], [3.0, 0.0]), 1.0)
        self.assertEqual(cosine_similarity([0.0, 0.0], [3.0, 0.0]), 0.0)

    def test_batch_knowledge_text_parser_preserves_multiline_content(self) -> None:
        parsed = parse_knowledge_text_file(
            "article.txt",
            "测试法律\n第十二条\n权威测试来源\n正文第一段。\n正文第二段。".encode(),
        )
        self.assertEqual(parsed.article.law_name, "测试法律")
        self.assertEqual(parsed.article.article_number, "第十二条")
        self.assertEqual(parsed.article.content, "正文第一段。\n正文第二段。")

    def test_batch_knowledge_text_parser_rejects_non_utf8(self) -> None:
        with self.assertRaises(KnowledgeImportError):
            parse_knowledge_text_file("article.txt", b"\xff\xfe\x00\x00")

    def test_agent_normalizer_converts_unstructured_text_to_four_line_protocol(self) -> None:
        raw = (
            "资料卡\n法规：《中华人民共和国食品安全法》\n"
            "条款编号：第四条\n出处：国家法律法规数据库\n"
            "内容如下：食品生产经营者对其生产经营食品的安全负责。"
        )
        filename, text = decode_unstructured_knowledge_file(
            "../unsafe name.txt",
            raw.encode("utf-8"),
        )
        llm = FakeNormalizerLLM(
            {
                "law_name": "中华人民共和国食品安全法",
                "article_number": "第四条",
                "source": "国家法律法规数据库",
                "content": "食品生产经营者对其生产经营食品的安全负责。",
                "confidence": 0.96,
                "warnings": [],
                "multiple_articles_detected": False,
            }
        )

        result = normalize_knowledge_text(filename, text, llm)  # type: ignore[arg-type]

        self.assertEqual(filename, "unsafe name.txt")
        self.assertTrue(result["ready_for_import"])
        self.assertTrue(result["requires_human_review"])
        self.assertEqual(
            result["standardized_text"],
            "中华人民共和国食品安全法\n第四条\n国家法律法规数据库\n"
            "食品生产经营者对其生产经营食品的安全负责。",
        )
        self.assertEqual(result["standardized_filename"], "unsafe_name_standardized.txt")

    def test_agent_normalizer_marks_missing_fields_and_multiple_articles(self) -> None:
        raw = "第一条 本办法适用于测试。\n第二条 其他要求另行规定。"
        llm = FakeNormalizerLLM(
            {
                "law_name": None,
                "article_number": "第一条",
                "source": None,
                "content": "本办法适用于测试。",
                "confidence": 0.42,
                "warnings": ["原文件包含多条内容"],
                "multiple_articles_detected": True,
            }
        )

        result = normalize_knowledge_text("mixed.txt", raw, llm)  # type: ignore[arg-type]

        self.assertFalse(result["ready_for_import"])
        self.assertEqual(result["missing_fields"], ["law_name", "source"])
        standardized_text = str(result["standardized_text"])
        self.assertIn("[待补充法律名称]", standardized_text)
        self.assertIn("[待补充来源]", standardized_text)
        self.assertTrue(result["multiple_articles_detected"])

    def test_generated_batch_law_corpus_has_200_valid_unique_articles(self) -> None:
        sample_dir = Path(__file__).resolve().parents[1] / "examples" / "batch_laws"
        files = sorted(sample_dir.glob("*.txt"))
        self.assertEqual(len(files), 200)

        keys: set[tuple[str, str]] = set()
        for path in files:
            parsed = parse_knowledge_text_file(path.name, path.read_bytes())
            key = (parsed.article.law_name, parsed.article.article_number)
            self.assertNotIn(key, keys)
            keys.add(key)
        self.assertEqual(len(keys), 200)


if __name__ == "__main__":
    unittest.main()
