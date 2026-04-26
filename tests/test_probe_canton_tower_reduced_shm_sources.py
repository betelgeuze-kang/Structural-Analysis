from pathlib import Path
import sys


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import probe_canton_tower_reduced_shm_sources as canton_probe  # noqa: E402


def test_extract_links_and_classify() -> None:
    html = """
    <html><body>
      <a href="Phase%20I%20data/system_matrices.mat">mat</a>
      <a href="Phase%20I%20data/Phase_I_measurement_description.pdf">pdf</a>
      <a href="Phase%20I%20data/Phase%20I%20data_all.zip">zip</a>
    </body></html>
    """
    links = canton_probe._extract_links("https://polyucee.hk/ceyxia/benchmark/task_i.htm", html)
    assert links == [
        "https://polyucee.hk/ceyxia/benchmark/Phase%20I%20data/system_matrices.mat",
        "https://polyucee.hk/ceyxia/benchmark/Phase%20I%20data/Phase_I_measurement_description.pdf",
        "https://polyucee.hk/ceyxia/benchmark/Phase%20I%20data/Phase%20I%20data_all.zip",
    ]
    assert canton_probe._classify(links[0]) == "system_matrices"
    assert canton_probe._classify(links[1]) == "benchmark_docs"
    assert canton_probe._classify(links[2]) == "measured_response"
