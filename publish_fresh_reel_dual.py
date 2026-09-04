from __future__ import annotations

import json
import time
from pathlib import Path

from dotenv import load_dotenv

from src.az_enterprise.core.promotion_candidate_analyzer_rc1 import (
    PromotionCandidateAnalyzerRC1,
)
from src.az_enterprise.core.promotion_render_runtime_rc1 import (
    PromotionRenderRuntimeRC1,
)
from src.az_enterprise.core.instagram_publication_runtime_rc1 import (
    InstagramPublicationRuntimeRC1,
)
from src.az_enterprise.core.tiktok_connector_rc1 import (
    TikTokConnectorRC1,
)


ROOT = Path(__file__).resolve().parent
PROJECT_ID = "amazonia"


def main() -> int:

    load_dotenv(ROOT / ".env", override=True)

    # 1. Analyze finished film and rank fresh promotion candidates.
    analyzer = PromotionCandidateAnalyzerRC1(
        project_id=PROJECT_ID,
        root=ROOT,
    )

    analysis = analyzer.analyze(
        top_k=20,
        min_duration_sec=18.0,
        target_duration_sec=32.0,
        max_duration_sec=52.0,
        maximum_overlap_ratio=0.35,
    )

    candidates = analyzer.promotion_candidates(
        analysis
    )

    if not candidates:
        raise RuntimeError(
            "No promotion candidates found"
        )

    # 2. Exclude already published Instagram candidates.
    instagram = InstagramPublicationRuntimeRC1(
        project_id=PROJECT_ID,
        root=ROOT,
    )

    published = instagram.published_candidate_ids()

    candidate = next(
        (
            item
            for item in candidates
            if item.candidate_id not in published
        ),
        None,
    )

    if candidate is None:
        raise RuntimeError(
            "No fresh unpublished candidate available"
        )

    print(
        "SELECTED:",
        candidate.candidate_id,
        candidate.source_start_sec,
        candidate.source_end_sec,
        candidate.reason,
    )

    # 3. Create one new canonical vertical master.
    renderer = PromotionRenderRuntimeRC1(
        project_id=PROJECT_ID,
        root=ROOT,
    )

    spec = renderer.build_spec(
        candidate_id=candidate.candidate_id,
        source_start_sec=candidate.source_start_sec,
        source_end_sec=candidate.source_end_sec,
    )

    master = renderer.render_spec(
        spec,
        overwrite=True,
    )

    print("MASTER:", master)

    # 4. Caption for both platforms.
    caption = (
        "Deep inside the Amazon, history, danger and mystery "
        "still hide beneath the world's largest rainforest. "
        "What are we still missing? "
        "#Amazon #Amazonia #Documentary #History #AtlasZero"
    )

    # 5. Publish to Instagram.
    instagram_result = instagram.publish_one(
        candidate_id=candidate.candidate_id,
        local_path=master,
        caption=caption,
        share_to_feed=True,
        allow_republish=False,
    )

    print(
        "INSTAGRAM: PUBLISHED",
        instagram_result.media_id,
    )

    # 6. TikTok creator capabilities.
    tiktok = TikTokConnectorRC1()

    creator = tiktok.creator_info()
    creator_data = creator.get("data", {})

    privacy_options = (
        creator_data.get("privacy_level_options")
        or []
    )

    # Sandbox-safe publishing.
    privacy = (
        "SELF_ONLY"
        if "SELF_ONLY" in privacy_options
        else privacy_options[0]
    )

    # 7. Initialize TikTok Direct Post.
    init = tiktok.init_direct_post(
        video_path=master,
        title=caption,
        privacy_level=privacy,
        disable_comment=False,
        disable_duet=False,
        disable_stitch=False,
    )

    data = init.get("data") or {}

    upload_url = str(
        data.get("upload_url") or ""
    )

    publish_id = str(
        data.get("publish_id") or ""
    )

    if not upload_url or not publish_id:
        raise RuntimeError(
            "TikTok init returned no upload_url/publish_id: "
            + json.dumps(init, ensure_ascii=False)
        )

    # 8. Upload the same fresh master.
    status = tiktok.upload_video(
        upload_url=upload_url,
        video_path=master,
    )

    print(
        "TIKTOK UPLOAD HTTP:",
        status,
    )

    # 9. Poll TikTok publication state.
    for attempt in range(12):

        result = tiktok.publish_status(
            publish_id
        )

        print(
            "TIKTOK STATUS:",
            json.dumps(
                result,
                ensure_ascii=False,
            ),
        )

        state = str(
            (result.get("data") or {}).get(
                "status",
                "",
            )
        ).upper()

        if state in {
            "PUBLISH_COMPLETE",
            "PUBLISHED",
        }:
            print("TIKTOK: PUBLISHED")
            break

        if state in {
            "FAILED",
            "PUBLISH_FAILED",
        }:
            raise RuntimeError(
                "TikTok publication failed"
            )

        time.sleep(5)

    print("DUAL PUBLICATION COMPLETE")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
