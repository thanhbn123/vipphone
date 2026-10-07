"""Bộ thử triển khai trực tiếp, gọi từ pytest.

Toàn bộ phép đo nằm ở ``deploy/tests/thu-deploy.sh`` (viết bằng bash vì thứ nó
kiểm là bash). File này chỉ để ``make test`` và CI chạy được bộ đó — một bộ thử
không nằm trong đường chạy mặc định là bộ thử sẽ mục đi mà không ai biết.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SUITE = REPO / "deploy" / "tests" / "thu-deploy.sh"


def test_bo_thu_trien_khai_dat() -> None:
    """Chạy toàn bộ bộ thử deploy; mã thoát khác 0 là không đạt."""
    assert SUITE.is_file(), f"thiếu {SUITE}"
    r = subprocess.run(["bash", str(SUITE)], cwd=REPO, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        pytest.fail(f"bộ thử deploy KHÔNG đạt (mã {r.returncode}):\n{r.stdout}\n{r.stderr}")
    # Chốt rằng nó thật sự đã chạy các ca, không phải thoát sớm với 0 ca.
    assert "KẾT QUẢ:" in r.stdout
    assert " 0 không đạt" in r.stdout


@pytest.mark.parametrize(
    "script",
    ["common.sh", "staging.sh", "production.sh", "rollback.sh", "backup.sh", "verify.sh"],
)
def test_cu_phap_script(script: str) -> None:
    """`bash -n` từng script. Rẻ, và bắt được lỗi cú pháp trước khi nó bắt mình."""
    p = REPO / "deploy" / script
    assert p.is_file(), f"thiếu {p}"
    r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, f"{script} lỗi cú pháp:\n{r.stderr}"


@pytest.mark.skipif(shutil.which("docker") is None, reason="máy này không có docker")
def test_dockerfile_build_duoc() -> None:
    """Chỉ chạy ở nơi CÓ docker. Máy Mac mini hiện không có, nên nó bị bỏ qua —
    và việc bị bỏ qua được in ra, chứ không im lặng thành 'đạt'."""
    r = subprocess.run(
        ["docker", "build", "-q", "-f", "deploy/Dockerfile", "-t", "vipphone-thu:ci", "."],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert r.returncode == 0, r.stderr[-3000:]
