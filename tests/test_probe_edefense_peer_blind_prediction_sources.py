from pathlib import Path
import sys


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import probe_edefense_peer_blind_prediction_sources as edefense_probe  # noqa: E402


def test_extract_links_for_edefense_probe() -> None:
    html = """
    <html><body>
      <a href="/sites/default/files/news_e-defense_blind_analysis_2009-article.pdf">pdf</a>
      <a href="/foo/bar.zip">zip</a>
    </body></html>
    """
    links = edefense_probe._extract_links("https://peer.berkeley.edu/2009-blind-analysis-contest-e-defense", html)
    assert links == [
        "https://peer.berkeley.edu/sites/default/files/news_e-defense_blind_analysis_2009-article.pdf",
        "https://peer.berkeley.edu/foo/bar.zip",
    ]


def test_extract_link_rows_preserves_anchor_text_and_normalizes_apps_peer_urls() -> None:
    html = """
    <html><body>
      <a href="http://apps.peer.berkeley.edu/assets/Experimentalresults.xlsx">Experimental Results</a>
      <a href="/prediction_contest/wp-content/uploads/2010/09/QA_blindprediction-1.pdf">Q&A PDF</a>
    </body></html>
    """
    rows = edefense_probe._extract_link_rows("https://apps.peer.berkeley.edu/prediction_contest/?page_id=768", html)
    assert rows == [
        {
            "page_url": "https://apps.peer.berkeley.edu/prediction_contest/?page_id=768",
            "link_url": "https://apps.peer.berkeley.edu/assets/Experimentalresults.xlsx",
            "anchor_text": "Experimental Results",
        },
        {
            "page_url": "https://apps.peer.berkeley.edu/prediction_contest/?page_id=768",
            "link_url": "https://apps.peer.berkeley.edu/prediction_contest/wp-content/uploads/2010/09/QA_blindprediction-1.pdf",
            "anchor_text": "Q&A PDF",
        },
    ]


def test_classify_artifact_marks_measured_response_dataset_and_support_docs() -> None:
    assert (
        edefense_probe._classify_artifact(
            "https://apps.peer.berkeley.edu/assets/Experimentalresults.xlsx",
            anchor_text="Experimental Results",
            page_url="https://apps.peer.berkeley.edu/prediction_contest/?page_id=768",
        )
        == "measured_response_dataset"
    )
    assert (
        edefense_probe._classify_artifact(
            "https://apps.peer.berkeley.edu/prediction_contest/wp-content/uploads/2010/09/QA_blindprediction-1.pdf",
            anchor_text="Questions & Answers",
            page_url="https://apps.peer.berkeley.edu/prediction_contest/?page_id=152",
        )
        == "measured_response_support_doc"
    )
