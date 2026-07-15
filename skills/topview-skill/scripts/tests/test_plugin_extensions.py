from pathlib import Path
import sys
import unittest
from types import SimpleNamespace


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import ai_image
import video_gen
from shared.cli_parsers import parse_json_or_named_media_list


class PluginExtensionTests(unittest.TestCase):
    def test_storyboard_body_uses_fixed_backend_parameters(self):
        args = SimpleNamespace(
            prompt="Hook, product demo, proof, CTA",
            cell_aspect_ratio="9:16",
            shot_count=6,
            target_duration_seconds=15,
            reference_images=None,
            board_id="board_123",
            quiet=True,
        )

        body = ai_image.build_storyboard_body(args, object())

        self.assertEqual(body["type"], "storyboardToVideo")
        self.assertEqual(body["model"], "GPT Image 2")
        self.assertEqual(body["aspectRatio"], "16:9")
        self.assertEqual(body["resolution"], "2K")
        self.assertEqual(body["generateCount"], 1)
        self.assertEqual(body["boardId"], "board_123")
        self.assertIn("strict 9:16 aspect ratio", body["prompt"])
        self.assertIn("exactly 6 cells", body["prompt"])
        self.assertIn("15s", body["prompt"])

    def test_storyboard_led_omni_payload_numbers_references(self):
        args = SimpleNamespace(
            model="Standard",
            prompt="Approved product video script",
            storyboard_image="file_storyboard",
            input_images=["product.png", "creator.png"],
            reference_image_descriptions=["the product photo", "the creator reference"],
            input_videos=None,
            aspect_ratio="9:16",
            resolution=720,
            duration=15,
            sound="on",
            count=1,
            internet_search=False,
            board_id=None,
            quiet=True,
        )

        body = video_gen.build_omni_body(args, object())

        self.assertEqual(
            body["inputImages"],
            [
                {"name": "Image1", "fileId": "file_storyboard"},
                {"name": "Image2", "fileId": "product.png"},
                {"name": "Image3", "fileId": "creator.png"},
            ],
        )
        self.assertIn("<<<Image1>>>", body["prompt"])
        self.assertIn("<<<Image2>>>", body["prompt"])
        self.assertIn("Approved product video script", body["prompt"])
        self.assertEqual(body["sound"], "on")
        self.assertTrue(body["prompt"].startswith("\u56fe\u4e00\uff08<<<Image1>>>\uff09\u662f\u5206\u955c\u53c2\u8003\u56fe"))
        self.assertIn("\u56fe\u4e8c\uff08<<<Image2>>>", body["prompt"])

    def test_cross_platform_media_parser_keeps_legacy_json(self):
        self.assertEqual(
            parse_json_or_named_media_list(["Image1=product.png", "creator.png"], "Image"),
            [
                {"name": "Image1", "fileId": "product.png"},
                {"name": "Image2", "fileId": "creator.png"},
            ],
        )
        self.assertEqual(
            parse_json_or_named_media_list(
                '[{"fileId":"file_abc","name":"Image1"}]', "Image"
            ),
            [{"fileId": "file_abc", "name": "Image1"}],
        )


if __name__ == "__main__":
    unittest.main()

