import pathlib
import subprocess
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class PipelineE2ETest(unittest.TestCase):
    def run_cmd(self, *args, timeout=300):
        proc = subprocess.run(
            list(args),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            self.fail(
                "Command failed with code {}: {}\nSTDOUT:\n{}\nSTDERR:\n{}".format(
                    proc.returncode,
                    " ".join(args),
                    proc.stdout,
                    proc.stderr,
                )
            )
        return proc

    def test_full_pipeline_headless(self):
        self.run_cmd("make", "-B", "parse", "compile", timeout=420)
        self.run_cmd("cmake", "-S", "rospovm", "-B", "rospovm/build", timeout=240)
        self.run_cmd(
            "cmake",
            "--build",
            "rospovm/build",
            "--target",
            "rospovm_headless",
            "-j",
            "2",
            timeout=420,
        )

        binary_path = REPO_ROOT / "rospos/build/rospos.rosp"
        self.assertTrue(
            binary_path.exists(), "Expected compiled binary rospos/build/rospos.rosp"
        )

        run_proc = subprocess.run(
            [
                str(REPO_ROOT / "rospovm/build/rospovm_headless"),
                str(binary_path),
                "--max-steps",
                "1000000",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=240,
            check=False,
        )

        if run_proc.returncode != 0:
            self.fail(
                "Headless VM run failed with code {}\nSTDOUT:\n{}\nSTDERR:\n{}".format(
                    run_proc.returncode,
                    run_proc.stdout,
                    run_proc.stderr,
                )
            )


if __name__ == "__main__":
    unittest.main()
