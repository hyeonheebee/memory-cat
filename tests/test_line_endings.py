"""줄바꿈이 잘못되면 그 파일을 쓰는 플랫폼에서만 깨진다.

Windows 배치 파일은 CRLF 여야 하고(cmd 가 LF 파일을 잘못 읽는다), macOS 쪽
스크립트는 LF 여야 한다(CRLF 면 shebang 이 깨진다). 둘 다 이 저장소의
테스트로는 실행해 볼 수 없는 플랫폼이라, 바이트로 확인한다.

.gitattributes 가 체크아웃 시 이걸 맞춰 주지만, 누가 손으로 저장하거나
패치가 섞어 놓으면 워킹트리에서 어긋날 수 있다. 여기서 잡는다.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _tracked(pattern):
    """숨김 디렉터리(.git, .venv, 에이전트 워크트리)는 저장소 파일이 아니다."""
    return sorted(
        path
        for path in ROOT.glob(pattern)
        if not any(part.startswith(".") for part in path.relative_to(ROOT).parts)
    )


def _counts(path):
    data = path.read_bytes()
    return {
        "crlf": data.count(b"\r\n"),
        "lf": data.count(b"\n"),
        "cr": data.count(b"\r"),
        "bom": data[:3] == b"\xef\xbb\xbf",
        "data": data,
    }


class LineEndingTests(unittest.TestCase):
    def test_batch_files_are_entirely_crlf(self):
        batch = _tracked("**/*.bat") + _tracked("**/*.cmd")
        self.assertTrue(batch, "배치 파일을 못 찾았다면 경로 규칙이 낡은 것이다")
        for path in batch:
            with self.subTest(path=path.relative_to(ROOT)):
                c = _counts(path)
                # 홀로 있는 LF 가 하나라도 있으면 cmd 가 줄을 잘못 센다.
                self.assertEqual(c["lf"], c["crlf"])
                self.assertEqual(c["cr"], c["crlf"])
                # 배치 파일 맨 앞의 BOM 은 cmd 가 첫 줄에서 걸려 넘어진다.
                self.assertFalse(c["bom"])
                # 마지막 줄에 개행이 없으면 cmd 가 그 줄을 놓칠 수 있다.
                self.assertTrue(c["data"].endswith(b"\r\n"))

    def test_unix_scripts_have_no_carriage_returns(self):
        scripts = _tracked("**/*.command") + _tracked("**/*.sh")
        self.assertTrue(scripts)
        for path in scripts:
            with self.subTest(path=path.relative_to(ROOT)):
                # CRLF 면 shebang 이 "/bin/bash\r" 가 되어 실행 자체가 안 된다.
                self.assertEqual(_counts(path)["cr"], 0)

    def test_the_codepage_is_set_before_any_non_ascii_byte(self):
        # 이 파일에는 한글이 들어 있다. 코드페이지를 맞추기 전에 한글 바이트가
        # 나오면 콘솔에 깨져 보이고, 파서가 어긋날 여지도 남는다.
        path = ROOT / "windows" / "build_exe.bat"
        before = []
        for line in path.read_bytes().decode("utf-8").splitlines():
            if line.strip().lower().startswith("chcp "):
                break
            before.append(line)
        else:
            self.fail("chcp 줄을 찾지 못했다")
        offenders = [line for line in before if not line.isascii()]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
