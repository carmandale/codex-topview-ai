from pathlib import Path
import py_compile
import unittest


class TopViewScriptCompileTests(unittest.TestCase):
    @staticmethod
    def _starts_with_frontmatter_at_byte_zero(contents):
        return contents.startswith((b"---\n", b"---\r\n"))

    def test_frontmatter_byte_zero_check_accepts_common_line_endings(self):
        self.assertTrue(self._starts_with_frontmatter_at_byte_zero(b"---\nname: example\n"))
        self.assertTrue(self._starts_with_frontmatter_at_byte_zero(b"---\r\nname: example\r\n"))
        self.assertFalse(
            self._starts_with_frontmatter_at_byte_zero(b"\xef\xbb\xbf---\nname: example\n")
        )
        self.assertFalse(self._starts_with_frontmatter_at_byte_zero(b"----\nname: example\n"))
        self.assertFalse(self._starts_with_frontmatter_at_byte_zero(b"---x\nname: example\n"))
        self.assertFalse(self._starts_with_frontmatter_at_byte_zero(b"---"))

    def test_skill_frontmatter_starts_at_first_byte(self):
        skills_dir = Path(__file__).resolve().parents[3]
        skill_paths = sorted(skills_dir.glob("*/SKILL.md"))

        self.assertTrue(skill_paths)

        for skill_path in skill_paths:
            with self.subTest(skill=skill_path.parent.name):
                self.assertTrue(
                    self._starts_with_frontmatter_at_byte_zero(skill_path.read_bytes()),
                    f"{skill_path} must start with YAML frontmatter at byte zero",
                )

    def test_topview_scripts_compile(self):
        scripts_dir = Path(__file__).resolve().parents[1]
        script_paths = sorted(
            path
            for path in scripts_dir.glob("*.py")
            if path.name != "__init__.py"
        )

        self.assertTrue(script_paths)

        for script_path in script_paths:
            with self.subTest(script=script_path.name):
                py_compile.compile(str(script_path), doraise=True)


if __name__ == "__main__":
    unittest.main()
