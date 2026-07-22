import unittest

from app.services.case_analyzer import analyze_case
from app.services.document_parser import UnsupportedDocumentError, extract_text
from app.services.embeddings import cosine_similarity, embed


class ServiceTests(unittest.TestCase):
    def test_contract_case_analysis(self) -> None:
        result = analyze_case(
            "原告：张三。被告未按合同交付货物，原告请求赔偿损失。",
            "被告是否构成违约？",
        )
        self.assertEqual(result.case_type, "合同纠纷")
        self.assertIn("张三", result.parties)
        self.assertTrue(result.claims)

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


if __name__ == "__main__":
    unittest.main()

