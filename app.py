import os
import time
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from database import (
    init_db,
    prospect_exists,
    insert_prospect,
    get_prospects_by_status,
    update_dm_and_approve,
    update_status,
    claim_for_sending,
    mark_replied,
)
from ai_service import analyze_and_draft_dm
from x_service import XOutreachClient

load_dotenv()
init_db()

st.set_page_config(
    page_title="GenAI Fund — X Outreach Agent",
    page_icon="🚀",
    layout="wide",
)

# --- SIDEBAR: CONFIGURATION & SAFETY CONTROLS ---
with st.sidebar:
    st.title("⚙️ System Configuration")
    dry_run = st.toggle(
        "🧪 Dry-Run Mode (Safe Simulation)",
        value=True,
        help="Enabled by default. Simulates X profile fetching, DM sending, and reply syncing without spending X API credits.",
    )

    st.subheader("🔑 API Credentials (BYOK)")
    gemini_key = st.text_input(
        "Gemini API Key *",
        value=os.getenv("GEMINI_API_KEY", ""),
        type="password",
    ).strip()

    selected_model = st.selectbox(
        "Gemini Model",
        options=["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"],
        index=0,
        help="Uses Gemini Flash for low latency and minimal cost (<$0.0001/profile), with automatic fallback to 2.5-flash.",
    )

    x_bearer = st.text_input(
        "X Bearer Token",
        value=os.getenv("X_BEARER_TOKEN", ""),
        type="password",
        disabled=dry_run,
    ).strip()
    x_api_key = st.text_input(
        "X API Key (Consumer Key)",
        value=os.getenv("X_API_KEY", ""),
        type="password",
        disabled=dry_run,
    ).strip()
    x_api_secret = st.text_input(
        "X API Secret (Consumer Secret)",
        value=os.getenv("X_API_SECRET", ""),
        type="password",
        disabled=dry_run,
    ).strip()
    x_access_token = st.text_input(
        "X Access Token (User)",
        value=os.getenv("X_ACCESS_TOKEN", ""),
        type="password",
        disabled=dry_run,
    ).strip()
    x_access_secret = st.text_input(
        "X Access Token Secret",
        value=os.getenv("X_ACCESS_TOKEN_SECRET", ""),
        type="password",
        disabled=dry_run,
    ).strip()

    delay_seconds = st.slider(
        "Rate-Limit Delay Between DMs (sec)",
        min_value=2 if dry_run else 30,
        max_value=180,
        value=3 if dry_run else 60,
        help="Enforces cooldown between consecutive DMs to respect X anti-spam limits.",
    )

    st.divider()
    st.caption(
        "**Platform Guardrails & Limits:**\n"
        "- **Idempotency:** Unique `x_user_id` + atomic SQLite state lock (`APPROVED -> SENDING -> SENT`) prevents duplicate DMs.\n"
        "- **Closed DMs (`403`):** Flagged as `DM_CLOSED` without blocking the queue.\n"
        "- **Live X API:** Requires active Pay-per-use credits or Basic tier with `Read + Write + Direct Message` permissions."
    )

# --- HEADER & METRICS ---
st.title("🚀 GenAI Fund — AI & Robotics Builder Outreach")
if dry_run:
    st.info(
        "🧪 **DRY-RUN MODE ACTIVE:** Using simulated Southeast Asia AI/Robotics builder profiles and mock DM delivery. "
        "Toggle off Dry-Run Mode in the left sidebar and enter your X API v2 credentials for live execution."
    )

drafted_list = get_prospects_by_status(["DRAFTED"])
approved_list = get_prospects_by_status(["APPROVED"])
sent_list = get_prospects_by_status(["SENT", "DM_CLOSED", "FAILED", "RATE_LIMITED"])
replied_list = get_prospects_by_status(["REPLIED"])

c1, c2, c3, c4 = st.columns(4)
c1.metric("📝 Pending Review (Drafted)", len(drafted_list))
c2.metric("✅ Ready to Send (Approved)", len(approved_list))
c3.metric("📤 Processed Outbound", len(sent_list))
c4.metric("💬 Replies Received", len(replied_list))

tab1, tab2, tab3, tab4 = st.tabs([
    "1️⃣ Discovery & Evidence",
    "2️⃣ HITL Review & Approve",
    "3️⃣ Safe Outbound Queue",
    "4️⃣ Outbound Log & Replies",
])

x_client = XOutreachClient(
    bearer_token=x_bearer,
    api_key=x_api_key,
    api_secret=x_api_secret,
    access_token=x_access_token,
    access_token_secret=x_access_secret,
    dry_run=dry_run,
)

# ==========================================
# TAB 1: DISCOVERY & AI EVIDENCE EXTRACTION
# ==========================================
with tab1:
    st.subheader("Discover AI & Robotics Builders, Founders & Researchers")
    mode = st.radio(
        "Target Input Mode:",
        ["Seed X Handles (Recommended)", "Keyword Search (Recent Tweets)"],
        horizontal=True,
    )

    if mode.startswith("Seed"):
        handles_input = st.text_area(
            "Enter X Handles (comma or newline separated):",
            value="@linh_embodied_ai, @arjun_llm_infra, @siti_ai_agents" if dry_run else "",
            placeholder="@chipro, @jimfan, @adcock_brett",
        )
        run_discovery = st.button("🔍 Fetch Profiles & Draft Personalized DMs", type="primary")
    else:
        keyword_input = st.text_input(
            "Enter Domain Keywords:",
            value="Embodied AI robotics founder" if dry_run else "",
            placeholder="VLA model OR robotics startup OR LLM inference",
        )
        run_discovery = st.button("🔍 Search & Draft Personalized DMs", type="primary")

    if run_discovery:
        if not gemini_key:
            st.error("Please enter your **Gemini API Key** in the left sidebar first.")
        elif not dry_run and not x_bearer:
            st.error("Live Mode requires an **X Bearer Token** in the left sidebar (or enable Dry-Run Mode).")
        else:
            with st.spinner("Fetching profile evidence and evaluating fit with Gemini..."):
                if mode.startswith("Seed"):
                    raw_items = [h.strip() for h in handles_input.replace("\n", ",").split(",") if h.strip()]
                    profiles, errs = x_client.fetch_by_handles(raw_items)
                else:
                    profiles, errs = x_client.search_by_keyword(keyword_input)

                for err in errs:
                    st.warning(err)

                added_count = 0
                skipped_count = 0
                for p in profiles:
                    if prospect_exists(p["x_user_id"]):
                        skipped_count += 1
                        continue

                    try:
                        eval_res = analyze_and_draft_dm(
                            api_key=gemini_key,
                            display_name=p["display_name"],
                            username=p["username"],
                            bio=p["bio"],
                            location=p["location"],
                            recent_tweets=p["recent_tweets"],
                            model_name=selected_model,
                        )
                        p["is_fit"] = eval_res.is_fit
                        p["fit_reason"] = eval_res.fit_reason
                        p["evidence_quote"] = eval_res.evidence_quote
                        p["dm_text"] = eval_res.personalized_dm
                        p["status"] = "DRAFTED" if eval_res.is_fit else "REJECTED"

                        if insert_prospect(p):
                            added_count += 1
                    except Exception as e:
                        st.error(f"Gemini evaluation error for @{p['username']}: {e}")

                st.success(
                    f"Discovery complete! Added **{added_count}** new prospect(s) "
                    f"(Skipped **{skipped_count}** duplicate(s) already in database)."
                )
                time.sleep(1)
                st.rerun()

# ==========================================
# TAB 2: HUMAN-IN-THE-LOOP APPROVAL
# ==========================================
with tab2:
    st.subheader("Human-in-the-Loop (HITL) Evidence Verification & DM Approval")
    if not drafted_list:
        st.info("No drafts pending review. Go to Tab 1 to discover and evaluate prospects.")
    else:
        for item in drafted_list:
            with st.container(border=True):
                col_info, col_dm = st.columns([1.1, 1.2])
                with col_info:
                    st.markdown(f"### {item['display_name']} (`@{item['username']}`)")
                    if item["location"]:
                        st.caption(f"📍 {item['location']}")
                    st.markdown(f"**Bio:** {item['bio']}")
                    st.success(f"**🎯 Why They Fit:** {item['fit_reason']}")
                    st.info(f"**📌 Verifiable Evidence:** {item['evidence_quote']}")
                    with st.expander("View Raw Collected Tweets"):
                        st.text(item["recent_tweets"])

                with col_dm:
                    edited_dm = st.text_area(
                        "Personalized DM Draft (Editable before approval):",
                        value=item["dm_text"],
                        height=140,
                        key=f"dm_edit_{item['x_user_id']}",
                    )
                    st.caption(f"Character count: {len(edited_dm)} / 280")

                    b1, b2 = st.columns(2)
                    if b1.button("✅ Approve & Queue", key=f"app_{item['x_user_id']}", type="primary"):
                        update_dm_and_approve(item["x_user_id"], edited_dm)
                        st.rerun()
                    if b2.button("🗑️ Reject", key=f"rej_{item['x_user_id']}"):
                        update_status(item["x_user_id"], "REJECTED", "Rejected by human reviewer")
                        st.rerun()

# ==========================================
# TAB 3: RATE-LIMITED SAFE OUTBOUND SENDER
# ==========================================
with tab3:
    st.subheader("Approved Outbound Queue (Idempotent & Rate-Limited)")
    if not approved_list:
        st.info("No approved DMs in queue. Approve drafts in Tab 2 first.")
    else:
        if not dry_run and not (x_api_key and x_api_secret and x_access_token and x_access_secret):
            st.warning(
                "⚠️ Live Mode is active, but OAuth 1.0a User Tokens (`API Key/Secret` & `Access Token/Secret`) are incomplete. "
                "Sending will fail until all 4 OAuth keys are entered in the sidebar."
            )

        st.write(f"**{len(approved_list)}** approved message(s) ready for dispatch:")
        for item in approved_list:
            st.markdown(f"- **@{item['username']}**: _{item['dm_text']}_")

        if st.button("🚀 Send Approved DMs", type="primary"):
            progress = st.progress(0)
            status_box = st.empty()

            for idx, item in enumerate(approved_list):
                uid = item["x_user_id"]
                if not claim_for_sending(uid):
                    status_box.warning(f"Skipped @{item['username']} (already claimed or sent).")
                    continue

                status_box.info(f"Dispatching DM to @{item['username']} ({idx + 1}/{len(approved_list)})...")
                send_status, err_msg = x_client.send_direct_message(uid, item["dm_text"])
                update_status(uid, send_status, err_msg)

                progress.progress((idx + 1) / len(approved_list))
                if idx < len(approved_list) - 1:
                    time.sleep(delay_seconds)

            status_box.success("Outbound batch completed!")
            time.sleep(1)
            st.rerun()

# ==========================================
# TAB 4: SENT LOGS & REPLY TRACKING
# ==========================================
with tab4:
    st.subheader("Campaign Audit Log & Reply Tracking")
    col_sync, col_export = st.columns([1.2, 4])
    if col_sync.button("🔄 Sync Incoming Replies"):
        sent_ids = [r["x_user_id"] for r in get_prospects_by_status(["SENT"])]
        replies = x_client.fetch_incoming_replies(sent_ids)
        for uid, text in replies.items():
            mark_replied(uid, text)
        st.success(f"Sync complete! Detected **{len(replies)}** new reply(ies).")
        time.sleep(1)
        st.rerun()

    all_records = get_prospects_by_status(["REPLIED", "SENT", "DM_CLOSED", "FAILED", "RATE_LIMITED", "REJECTED"])
    if all_records:
        df = pd.DataFrame(all_records)[
            ["username", "display_name", "status", "dm_text", "reply_text", "sent_at", "error_log"]
        ]
        st.dataframe(df, use_container_width=True)

        csv_data = df.to_csv(index=False).encode("utf-8")
        col_export.download_button(
            "📥 Export CSV Log",
            data=csv_data,
            file_name="genaifund_outreach_log.csv",
            mime="text/csv",
        )
    else:
        st.info("No outbound history recorded yet.")
