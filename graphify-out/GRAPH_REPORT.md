# Graph Report - project-analysis-skills-6b0083  (2026-11-21)

## Corpus Check
- 180 files · ~102,639 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 30 file(s) not represented in the graph (top: .xml 13, (none) 7, .ini 2)

## Summary
- 2465 nodes · 5957 edges · 120 communities (88 shown, 32 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 227 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `212f7735`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Android ViewModel Tests
- test_torch_engine.py
- Multi-Analysis Client Flow
- Image Preprocessing
- Result Screen UI
- Model Training Scripts
- Camera & Language UI
- Contract Test DB Shim
- App Locale & Bootstrap
- Config & Mode Enforcement
- Backend Spec & Deployment
- Image Quality Gate
- Non-Fundus Analysis API
- Predict Endpoint Pipeline
- Inference Engine Interface
- Grad-CAM Heatmaps
- Eye-Care Preferences & Reminders
- ScreeningHistoryEntity
- App Navigation Root
- History Screen UI
- PomodoroScreen.kt
- Screening ViewModel States
- TorchEngine
- App Startup & Security
- Exam Persistence Queries
- Encrypted Room Database
- Analyzer Catalog
- Duplicate Retry Tests
- Route Dependencies & Exams
- EyeCareComponents.kt
- Audit Regression Tests
- PupilHeuristicsTest
- predictAndAwait
- find_checkpoint
- Integration Auth Tests
- Bitmap Loading
- Error Detail Wire Tests
- Analyze Endpoint Tests
- Error Envelope Tests
- Rate Limit Tests
- Offline Upload Queue
- Async Worker & Engine Factory
- typing
- Contract Auth Tests
- Predict Contract Tests
- get_engine
- Shared Test Fixtures
- Focus Shift Exercise
- Eye Symmetry Analysis
- ScreeningHistoryDatabase
- Error Envelope Core
- Synthetic Test Images
- DR Data Prep & Eval
- IrisLandmarker.kt
- Superpowers Design Docs
- Follow-Dot Exercise
- ScreeningViewModel.kt
- DB Failure Contract Tests
- Model Unavailable Tests
- Static Serving Integration
- Pomodoro Timer
- Offline DR Classifier
- Pomodoro Worker Tests
- Predict Step Failure Tests
- Latency Perf Guard
- Database Key Provider
- Blink & Palm Exercise
- ReminderSettingsViewModel
- Screen Routes
- Frame Quality Levels
- Admin Dashboard
- ReminderWorker.kt
- HistoryViewModel
- Screening History DAO
- limits.py
- Smoke Test Script
- Static Serving Contract
- Ungradable Wire Tests
- DB Failure Integration
- Skin Data Fetch & Frozen Kit
- Reminder Worker Tests
- Engine Spy Safety Test
- Async Predict Tests
- Clean Code Principles
- Eye Side Labels
- _install_in_memory_crud
- Rate Limit Middleware
- Spec Contracts C1-C10
- Android Plan & Upload Hygiene
- test_error_detail_is_string.py
- Stream Cap Regression
- Spec v4 Agent B DB
- Model & Asset READMEs
- .__init__
- Client Evidence Contracts
- Notification Helper
- Android README & Schema
- Settings
- DB Engine Disposal
- Health & API Key Auth
- download_model.py
- UiState
- Android AppConfig
- Demo Data Policy
- get_engine
- Common AppConfig
- iOS AppConfig
- Backend verify & run (backend/)
- Models: train → evaluate → ship
- CLAUDE.md — EYE DETECT AI
- Backend ⇄ app wire contract

## God Nodes (most connected - your core abstractions)
1. `upload()` - 94 edges
2. `get_settings()` - 54 edges
3. `EyeCarePreferencesRepository` - 42 edges
4. `ScreeningViewModelTest` - 39 edges
5. `load_rgb()` - 35 edges
6. `ScreeningViewModel` - 34 edges
7. `QualityLevel` - 26 edges
8. `predict()` - 25 edges
9. `ModelUnavailable` - 25 edges
10. `assess()` - 25 edges

## Surprising Connections (you probably didn't know these)
- `Things that bite` --references--> `ScreeningHistoryDatabase`  [INFERRED]
  .claude/skills/android-build/SKILL.md → composeApp/src/androidMain/kotlin/com/eyedetect/ai/data/history/ScreeningHistoryDatabase.kt
- `dr_model.tflite (1x224x224x3 float32 input, 5 logits)` --semantically_similar_to--> `Diabetic retinopathy EfficientNet-B0 model (dr-effb0-aptos-idrid-v2)`  [INFERRED] [semantically similar]
  composeApp/src/androidMain/assets/README.md → training/README.md
- `Where the contract lives` --references--> `ExamSummary`  [INFERRED]
  .claude/skills/api-contract/SKILL.md → backend/app/schemas.py
- `Where the contract lives` --references--> `ErrorEnvelope`  [INFERRED]
  .claude/skills/api-contract/SKILL.md → backend/app/schemas.py
- `main()` --calls--> `get_settings()`  [INFERRED]
  training/eval_backend_dr.py → backend/app/config.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **opencv headless fix applied in venv, Docker, CI** — backend_readme_opencv_trap, github_workflows_backend_ci_lint_job, github_workflows_backend_ci_test_job, backend_requirements [EXTRACTED 0.95]
- **Four parallel agent worktrees built on frozen kit** — backend_spec_v4_agent_a_inference, backend_spec_v4_agent_b_db, backend_spec_v4_agent_c_api, backend_spec_v4_agent_d_ops, backend_spec_v4_frozen_interface_kit [EXTRACTED 1.00]
- **Screening flow across Clean Architecture layers** — docs_superpowers_specs_2026_07_31_clean_architecture_refactor_design_screeningviewmodel, docs_superpowers_specs_2026_07_31_clean_architecture_refactor_design_submitscreeningusecase, docs_superpowers_specs_2026_07_31_clean_architecture_refactor_design_screeningrepository, docs_superpowers_specs_2026_07_31_clean_architecture_refactor_design_screeningresult [EXTRACTED 1.00]
- **Four parallel Phase 1 agents with disjoint ownership** — backend_spec_agent_a_inference, backend_spec_agent_b_db, backend_spec_agent_c_api, backend_spec_agent_d_ops [EXTRACTED 1.00]
- **PHI security hardening measures** — docs_superpowers_specs_2026_08_03_security_hardening_design_api_key_auth, docs_superpowers_specs_2026_08_03_security_hardening_design_network_security_config, docs_superpowers_specs_2026_08_03_security_hardening_design_http_logging_level, docs_superpowers_specs_2026_08_03_security_hardening_design_temp_file_cleanup [EXTRACTED 1.00]
- **SOLID principles** — clean_code_solid_dry_kiss_srp, clean_code_solid_dry_kiss_ocp, clean_code_solid_dry_kiss_lsp, clean_code_solid_dry_kiss_isp, clean_code_solid_dry_kiss_dip [EXTRACTED 1.00]
- **Predict safety invariants (quality gate, persistence, dedup)** — backend_spec_quality_gate, backend_spec_c10_strict_persistence, backend_spec_c14_idempotency_dedup, backend_spec_c3_ungradable_split_truth [INFERRED 0.85]
- **Android retry/health/detail behaviors driving backend contract** — plan_retry_resend_same_file, plan_health_ping_head, plan_http_error_detail_mapping, backend_spec_v4_c14_idempotency_dedup, backend_spec_v4_c16_head_root_health, backend_spec_v4_c15_error_detail_uzbek_string [INFERRED 0.95]

## Communities (120 total, 32 thin omitted)

### Community 0 - "Android ViewModel Tests"
Cohesion: 0.06
Nodes (12): configureApi(), PredictPolling, PredictResponse, TaskResponse, TaskStatusResponse, ApiServiceTest, FakeApiService, FakeHistoryStore (+4 more)

### Community 1 - "test_torch_engine.py"
Cohesion: 0.12
Nodes (13): resolve_device(), _bare_engine(), _samples_present(), test_an_unknown_device_degrades_to_cpu(), test_auto_and_mps_pick_mps_when_available(), test_auto_picks_cpu_without_mps(), test_cpu_is_honoured_verbatim(), test_digest_mismatch_is_detected_before_any_torch_load() (+5 more)

### Community 2 - "Multi-Analysis Client Flow"
Cohesion: 0.05
Nodes (13): AnalysisUiState, AnalysisViewModel, Error, Idle, Loading, Success, AnalysisApi, AnalysisFinding (+5 more)

### Community 3 - "Image Preprocessing"
Cohesion: 0.08
Nodes (28): _as_rgb_uint8(), display_copy(), load_rgb(), retina_crop(), to_model_input(), render(), _jpeg(), test_display_copy_is_512px_rgb_uint8() (+20 more)

### Community 4 - "Result Screen UI"
Cohesion: 0.09
Nodes (39): EyeSymmetryUiState, ExerciseCompletionCard(), ClinicalDetailCard(), DisclaimerText(), ErrorState(), EyeSelector(), EyeSymmetryCard(), formatProbabilityPercent() (+31 more)

### Community 5 - "Model Training Scripts"
Cohesion: 0.08
Nodes (13): Fundus, main(), metrics(), normalise(), predict(), seed_all(), Lesions, load_images() (+5 more)

### Community 6 - "Camera & Language UI"
Cohesion: 0.08
Nodes (10): CameraScreen(), OnImageSavedCallback, CaptureReviewSheet(), fileLabel(), FlashModeChip(), GalleryPickSheet(), InfoBanner(), SecondaryButton() (+2 more)

### Community 7 - "Contract Test DB Shim"
Cohesion: 0.06
Nodes (9): _build_db_base(), get_session(), _build_gradcam(), _build_preprocess(), _FakeSession, install(), stubbed_modules(), _StubFinder (+1 more)

### Community 8 - "App Locale & Bootstrap"
Cohesion: 0.06
Nodes (7): EyeCareApp, LocalePrefs, cleanupStaleCaptures(), MainActivity, EyeDetectTheme(), MainFlowTest, ResultScreenTest

### Community 9 - "Config & Mode Enforcement"
Cohesion: 0.10
Nodes (24): decide(), grade_for_mean(), mean_gray(), MockEngine, _build_quality(), assess(), decode_rgb(), blur_var() (+16 more)

### Community 10 - "Backend Spec & Deployment"
Cohesion: 0.06
Nodes (31): backend CLAUDE.md (agent rules), Two input domains reach engine.predict (RGB HWC vs normalised CHW), docker-compose.yml (api, admin, postgres services), compose admin service (streamlit), compose api service, compose postgres service (prod profile), backend README.md, DERETFound_DR_APTOS2019 staged checkpoint (unvalidated) (+23 more)

### Community 11 - "Image Quality Gate"
Cohesion: 0.11
Nodes (22): _as_rgb_uint8(), assess(), blur_variance(), mean_gray(), QualityReport, QualitySettings, _decode(), StubSettings (+14 more)

### Community 12 - "Non-Fundus Analysis API"
Cohesion: 0.11
Nodes (16): get_type(), AnalysisTypeOut, AnalyzeResponse, FindingOut, analyze(), _find_duplicate(), _findings(), get_analysis() (+8 more)

### Community 13 - "Predict Endpoint Pipeline"
Cohesion: 0.10
Nodes (16): _clean(), _lookup_replay(), _persist(), predict(), predict_async(), _read_capped(), _render_heatmap(), _to_tensor() (+8 more)

### Community 14 - "Inference Engine Interface"
Cohesion: 0.14
Nodes (4): ModelUnavailable, Prediction, OnnxEngine, export_model()

### Community 15 - "Grad-CAM Heatmaps"
Cohesion: 0.11
Nodes (24): _as_batched_tensor(), _as_rgb_uint8(), mock_heatmap(), _overlay(), _pick_target_layer(), render_heatmap(), _write_png(), _assert_valid_png() (+16 more)

### Community 17 - "ScreeningHistoryEntity"
Cohesion: 0.17
Nodes (3): ScreeningHistoryEntity, ScreeningHistoryRepository, ScreeningHistoryStore

### Community 18 - "App Navigation Root"
Cohesion: 0.08
Nodes (14): AppRoot(), AnalysisCaptureScreen(), AnalysisResultContent(), AnalysisResultScreen(), AnalysisTypeScreen(), DetailRow(), FindingRow(), newCaptureUri() (+6 more)

### Community 19 - "History Screen UI"
Cohesion: 0.08
Nodes (6): HistoryEntryCard(), HistoryScreen(), localizedQuality(), PendingUploadCard(), decisionColor(), decisionIcon()

### Community 21 - "Screening ViewModel States"
Cohesion: 0.15
Nodes (5): PendingUploadStore, FromFile, FromGalleryUri, ScreeningViewModel, UploadSource

### Community 22 - "TorchEngine"
Cohesion: 0.14
Nodes (9): TorchEngine, _checkpoint_dir(), StubSettings, test_a_checkpoint_with_the_wrong_class_count_is_refused(), test_digest_mismatch_refuses_to_load(), test_engine_is_deterministic(), test_engine_loads_and_predicts_a_distribution(), test_missing_artifact_raises_a_clear_error() (+1 more)

### Community 23 - "App Startup & Security"
Cohesion: 0.07
Nodes (18): engine_for(), require_api_key(), get_settings(), auth_disabled(), verify_api_key(), warn_if_unprotected(), create_app(), health() (+10 more)

### Community 24 - "Exam Persistence Queries"
Cohesion: 0.08
Nodes (35): find_by_idempotency_key(), find_recent_duplicate(), get_exam(), list_exams(), _newest_exam_within(), _select_by_patient_code(), PredictResponse, _count() (+27 more)

### Community 26 - "Analyzer Catalog"
Cohesion: 0.13
Nodes (13): Analyzer, colour_cue(), get_analyzer(), is_real_model_available(), MockAnalyzer, model_path(), OnnxAnalyzer, _softmax() (+5 more)

### Community 27 - "Duplicate Retry Tests"
Cohesion: 0.11
Nodes (15): engine_calls(), post(), test_a_different_patient_is_a_new_exam(), test_a_key_takes_precedence_over_the_fingerprint(), test_blank_patient_id_retry_keeps_the_generated_code(), test_blank_patient_id_retry_replays_the_same_exam(), test_blank_patient_id_retry_with_no_eye_also_replays(), test_blank_patient_id_still_separates_the_two_eyes() (+7 more)

### Community 28 - "Route Dependencies & Exams"
Cohesion: 0.11
Nodes (14): fill_additive_keys(), _detail(), get_exam(), _list(), list_exams(), get_predict_status(), _load(), get_session() (+6 more)

### Community 29 - "EyeCareComponents.kt"
Cohesion: 0.08
Nodes (10): DotTrackerCanvas(), GameCard(), IntervalChipRow(), MenuCard(), TimerRing(), LanguagePicker(), formatClock(), PomodoroScreen() (+2 more)

### Community 30 - "Audit Regression Tests"
Cohesion: 0.09
Nodes (22): _assert_uzbek_detail(), _boom(), cyrillic_key_client(), _LoadedEngine, shadow_client(), small_cap_client(), test_a_correct_key_still_works(), test_a_correct_non_ascii_key_is_accepted() (+14 more)

### Community 31 - "PupilHeuristicsTest"
Cohesion: 0.08
Nodes (5): EyeDetectionAnalyzer, EyePosition, EyeRegion, PupilHeuristics, PupilHeuristicsTest

### Community 32 - "predictAndAwait"
Cohesion: 0.19
Nodes (4): ApiService, predictAndAwait(), PredictFailedException, PredictTimeoutException

### Community 33 - "find_checkpoint"
Cohesion: 0.13
Nodes (14): _arch_from_hf_config(), find_checkpoint(), _read_arch(), sha256_file(), test_find_checkpoint_accepts_a_local_hf_snapshot_subdir(), test_find_checkpoint_defaults_to_imagenet_normalisation_when_absent(), test_find_checkpoint_ignores_a_malformed_mean_std(), test_find_checkpoint_prefers_safetensors_over_pickle() (+6 more)

### Community 34 - "Integration Auth Tests"
Cohesion: 0.11
Nodes (12): build_client(), purge_app_modules(), keyed_client(), test_a_configured_key_logs_no_such_warning(), test_a_second_client_without_default_headers_is_anonymous(), test_api_paths_are_all_guarded(), test_auth_rejection_never_reaches_the_database(), test_comparison_is_constant_time() (+4 more)

### Community 36 - "Error Detail Wire Tests"
Cohesion: 0.19
Nodes (8): post_predict(), _post(), upload(), test_blank_patient_id_is_treated_as_missing(), test_generated_code_is_persisted_not_just_returned(), test_generated_codes_are_distinct_per_exam(), test_missing_patient_id_gets_a_server_code(), test_provided_patient_id_is_echoed_verbatim()

### Community 37 - "Analyze Endpoint Tests"
Cohesion: 0.21
Nodes (15): _photo(), _post(), shadow_client(), test_analyze_requires_api_key(), test_blurry_photo_is_ungradable(), test_dr_predict_contract_is_untouched(), test_duplicate_upload_replays_instead_of_creating(), test_every_type_returns_a_full_result() (+7 more)

### Community 38 - "Error Envelope Tests"
Cohesion: 0.16
Nodes (12): assert_envelope(), test_bad_eye_value_is_422(), test_empty_upload_is_invalid_image(), test_engine_failure_is_500_inference_error(), test_method_not_allowed_still_uses_the_envelope(), test_missing_file_part_is_a_string_detail_422(), test_no_error_response_ever_has_a_list_detail(), test_oversized_upload_is_413() (+4 more)

### Community 39 - "Rate Limit Tests"
Cohesion: 0.16
Nodes (14): _assert_uzbek_429(), _scope(), test_429_still_carries_cors_headers(), test_a_different_client_ip_has_its_own_quota(), inner(), test_a_path_outside_the_prefix_is_never_limited(), inner(), send() (+6 more)

### Community 41 - "Async Worker & Engine Factory"
Cohesion: 0.13
Nodes (3): InferenceEngine, _get_engine(), init_worker()

### Community 42 - "typing"
Cohesion: 0.07
Nodes (23): _read(), analysis_to_wire(), create_analysis(), get_analysis(), list_analyses(), init_db(), create_exam_with_result(), _create_patient_with_generated_code() (+15 more)

### Community 43 - "Contract Auth Tests"
Cohesion: 0.17
Nodes (11): anonymous(), test_correct_key_is_accepted(), test_exams_list_is_guarded_too(), test_head_root_answers_with_a_wrong_key(), test_head_root_answers_without_a_key(), test_health_is_open(), test_key_prefix_is_not_enough(), test_missing_key_is_401() (+3 more)

### Community 44 - "Predict Contract Tests"
Cohesion: 0.17
Nodes (14): body(), test_all_fifteen_legacy_keys_present(), test_body_validates_against_the_frozen_schema(), test_decision_and_quality_are_in_the_frozen_enums(), test_disclaimer_is_the_frozen_string(), test_exactly_seventeen_keys_and_nothing_invented(), test_eye_is_optional_and_echoed_as_null(), test_field_types() (+6 more)

### Community 45 - "get_engine"
Cohesion: 0.25
Nodes (3): _build(), _connect_args(), get_engine()

### Community 46 - "Shared Test Fixtures"
Cohesion: 0.20
Nodes (8): authed_client(), blurry_jpeg_bytes(), _build_app(), client(), dark_jpeg_bytes(), norefer_jpeg_bytes(), _purge_app_modules(), text_file_bytes()

### Community 47 - "Focus Shift Exercise"
Cohesion: 0.13
Nodes (8): Completed, FocusPhase, Far, Near, FocusShiftUiState, FocusShiftViewModel, Idle, Running

### Community 48 - "Eye Symmetry Analysis"
Cohesion: 0.25
Nodes (4): EyeSymmetryAnalyzer, EyeSymmetryResult, EyeSymmetrySample, EyeSymmetryAnalyzerTest

### Community 49 - "ScreeningHistoryDatabase"
Cohesion: 0.13
Nodes (5): Android app (composeApp/), Commands (run from repo root), local.properties (repo root, git-ignored, never commit), Things that bite, ScreeningHistoryDatabase

### Community 50 - "Error Envelope Core"
Cohesion: 0.18
Nodes (9): _detail_for(), _envelope(), _name_for(), register_handlers(), _api_error(), _http(), _unhandled(), _validation() (+1 more)

### Community 51 - "Synthetic Test Images"
Cohesion: 0.20
Nodes (8): main(), blurry_jpeg(), calibrated_jpeg(), dark_jpeg(), encode_jpeg(), norefer_jpeg(), not_an_image(), refer_jpeg()

### Community 52 - "DR Data Prep & Eval"
Cohesion: 0.17
Nodes (7): _framed(), test_retina_crop_threshold_is_the_specified_one(), test_retina_crop_trims_the_black_border(), main(), convert(), main(), to_pixels()

### Community 54 - "Superpowers Design Docs"
Cohesion: 0.14
Nodes (16): Release API URL Implementation Plan, checkReleaseSecrets Gradle guard task, RELEASE_API_URL local.properties setting, Security and PHI hardening implementation plan, Clean Architecture refactor design spec, Hilt NetworkModule, ScreeningRepository interface and ScreeningRepositoryImpl, ScreeningResult domain model and Decision enum (+8 more)

### Community 55 - "Follow-Dot Exercise"
Cohesion: 0.21
Nodes (6): runPhase(), Completed, FollowDotUiState, FollowDotViewModel, Idle, Running

### Community 57 - "DB Failure Contract Tests"
Cohesion: 0.26
Nodes (7): _explode(), test_a_retry_after_a_recovered_database_succeeds(), test_authenticated_mode_behaves_identically(), test_failure_detail_never_leaks_the_database_error(), test_no_verdict_is_returned_alongside_the_failure(), test_ungradable_persistence_failure_also_fails_the_request(), test_write_failure_is_500_persistence_error()

### Community 58 - "Model Unavailable Tests"
Cohesion: 0.17
Nodes (7): shadow_client(), test_demo_mode_readiness_is_200(), test_health_reports_the_model_as_not_loaded(), test_liveness_and_ping_still_answer(), test_no_mock_prediction_is_ever_served(), test_predict_is_503_model_unavailable(), test_readiness_is_503_without_a_verified_artifact()

### Community 59 - "Static Serving Integration"
Cohesion: 0.24
Nodes (9): created(), storage_root(), test_a_rejected_upload_leaves_no_file_behind(), test_an_ungradable_exam_writes_the_original_but_no_heatmap(), test_heatmap_png_is_on_disk(), test_original_bytes_are_on_disk_unmodified(), test_png_upload_is_stored_with_a_png_extension(), test_served_bytes_equal_the_bytes_on_disk() (+1 more)

### Community 60 - "Pomodoro Timer"
Cohesion: 0.17
Nodes (5): PomodoroPhase, BREAK, FOCUS, PomodoroState, PomodoroViewModel

### Community 63 - "Predict Step Failure Tests"
Cohesion: 0.35
Nodes (10): _explode(), _explode_disk(), test_a_retry_after_a_recovered_dedup_lookup_succeeds(), test_dedup_failure_never_leaks_the_database_error(), test_dedup_lookup_failure_creates_no_exam(), test_dedup_lookup_failure_is_500_inference_error(), test_idempotency_lookup_failure_is_500_inference_error(), test_save_original_failure_creates_no_exam() (+2 more)

### Community 64 - "Latency Perf Guard"
Cohesion: 0.25
Nodes (9): refer_jpeg_bytes(), _percentile(), _predict(), test_four_concurrent_predicts_each_finish_under_25s(), one(), test_mock_predict_p95_under_300ms(), test_the_semaphore_is_released_under_concurrency(), one() (+1 more)

### Community 66 - "Blink & Palm Exercise"
Cohesion: 0.23
Nodes (6): BlinkingRunning, BlinkPalmUiState, BlinkPalmViewModel, Completed, Idle, PalmingRunning

### Community 67 - "ReminderSettingsViewModel"
Cohesion: 0.11
Nodes (11): ExerciseStats, ExerciseType, BlinkPalm, FocusShift, FollowDot, isToday(), ReminderSettings, ReminderScheduler (+3 more)

### Community 68 - "Screen Routes"
Cohesion: 0.13
Nodes (15): Screen, AnalysisCapture, AnalysisResult, AnalysisTypes, BlinkPalm, Camera, EyeCareMenu, FocusShift (+7 more)

### Community 69 - "Frame Quality Levels"
Cohesion: 0.22
Nodes (6): QualityLevel, BAD, GOOD, WARN, FrameQuality, FrameQualityAnalyzer

### Community 70 - "Admin Dashboard"
Cohesion: 0.22
Nodes (5): _absolute(), fetch_exam(), fetch_exams(), _headers(), _table_row()

### Community 75 - "Smoke Test Script"
Cohesion: 0.26
Nodes (11): bold(), fail(), green(), pass(), predict(), red(), smoke_test.sh script, usage() (+3 more)

### Community 76 - "Static Serving Contract"
Cohesion: 0.24
Nodes (8): created(), test_client_filename_is_ignored(), test_heatmap_url_serves_a_png(), test_image_url_round_trips_the_exact_bytes(), test_image_url_serves_the_original_jpeg(), test_media_is_named_from_the_server_exam_id(), test_static_mount_does_not_escape_the_storage_root(), test_unknown_media_path_is_404()

### Community 77 - "Ungradable Wire Tests"
Cohesion: 0.23
Nodes (7): blurry_body(), test_blurry_image_is_ungradable(), test_dark_image_is_also_ungradable(), test_no_heatmap_for_an_ungradable_image(), test_placeholders_are_non_null(), test_ungradable_body_still_validates(), test_ungradable_exam_reads_back_with_the_same_placeholders()

### Community 78 - "DB Failure Integration"
Cohesion: 0.16
Nodes (7): _explode(), test_a_read_failure_does_not_masquerade_as_persistence_error(), test_failed_write_leaves_no_exam_in_the_history(), test_media_written_before_a_failed_write_is_not_advertised(), test_retry_after_recovery_yields_exactly_one_row(), test_shadow_mode_refuses_the_mock_engine(), test_shadow_mode_requires_a_digest()

### Community 79 - "Skin Data Fetch & Frozen Kit"
Cohesion: 0.23
Nodes (6): test_all_fifteen_legacy_keys_present(), test_golden_validates_against_frozen_schema(), download(), get_json(), main(), search()

### Community 81 - "Engine Spy Safety Test"
Cohesion: 0.32
Nodes (5): _landmine(), test_blurry_image_never_reaches_the_engine(), test_dark_image_never_reaches_the_engine(), test_the_landmine_really_does_fire_on_a_gradable_image(), test_the_quality_gate_sees_the_full_image_not_the_crop()

### Community 82 - "Async Predict Tests"
Cohesion: 0.35
Nodes (8): eager(), _submit(), test_a_resent_payload_replays_the_stored_exam(), test_async_flow_returns_the_same_wire_shape_as_sync(), test_bad_input_is_rejected_synchronously(), test_invalid_eye_is_rejected_synchronously(), test_missing_eye_stays_null_instead_of_defaulting_to_right(), test_unknown_replay_id_reports_failure()

### Community 83 - "Clean Code Principles"
Cohesion: 0.20
Nodes (3): Clean Code, SOLID, DRY, KISS guide (Kotlin/Android), Code review checklist and AI assistant prompt, Test coverage (ScreeningViewModelTest, ApiServiceTest, UI tests)

### Community 84 - "Eye Side Labels"
Cohesion: 0.31
Nodes (5): Eye, LEFT, RIGHT, eyeLabel(), eyeShortLabel()

### Community 85 - "_install_in_memory_crud"
Cohesion: 0.24
Nodes (7): _build_crud(), _install_in_memory_crud(), create_exam_with_result(), find_by_idempotency_key(), find_recent_duplicate(), _fresh(), _wire_row()

### Community 87 - "Spec Contracts C1-C10"
Cohesion: 0.22
Nodes (5): Agent A: inference (preprocess, quality, torch_engine, gradcam), InferenceEngine Protocol and get_engine factory, MockEngine (intensity-band deterministic), POST /predict flow (11 steps), Quality gate before verdict

### Community 88 - "Android Plan & Upload Hygiene"
Cohesion: 0.22
Nodes (9): Android PLAN.md (Keyingi ishlar rejasi), Compose back-stack navigation with rememberSaveable, Camera and quality control (FrameQualityAnalyzer), BitmapLoader.compressForUpload, Offline history (Room) and symmetry comparison, PupilHeuristics with MediaPipe IrisLandmarker, Release readiness (R8 minify, icon, build types, semver), Security and PHI hardening (+1 more)

### Community 89 - "test_error_detail_is_string.py"
Cohesion: 0.35
Nodes (6): error_responses(), _explode(), test_every_error_path_returns_a_non_empty_string_detail(), test_inference_error_detail_is_a_string(), test_persistence_error_detail_is_a_string(), test_unauthorized_detail_is_a_string()

### Community 90 - "Stream Cap Regression"
Cohesion: 0.17
Nodes (9): MaxBodySizeMiddleware, test_raw_stream_cap_aborts_a_chunked_body(), never_called(), receive(), send(), test_raw_stream_cap_lets_a_small_body_through(), inner(), receive() (+1 more)

### Community 91 - "Spec v4 Agent B DB"
Cohesion: 0.25
Nodes (7): Backend Spec v4 (Parallel Worktree Execution Plan), Agent B: db (models, base, crud bodies), CRUD frozen signatures (create_exam_with_result, find_recent_duplicate), DB schema (patients, exams, results, audit_log), decide() decision logic (REFER/NO_REFER/UNGRADABLE), Frozen interface kit (schemas, engine Protocol, CRUD signatures), Pilot-phase deferred items (C7: RLS, consent, outbox, MinIO)

### Community 92 - "Model & Asset READMEs"
Cohesion: 0.22
Nodes (8): Android assets README (dr_model.tflite placeholder note), dr_model.tflite (1x224x224x3 float32 input, 5 logits), Model training README, APTOS 2019 dataset, Diabetic retinopathy EfficientNet-B0 model (dr-effb0-aptos-idrid-v2), IDRiD dataset (official test split), ISIC Archive CC-0/CC-BY skin dataset, Skin lesion EfficientNet-B0 ONNX model (skin-effb0-isic-ccby)

### Community 93 - ".__init__"
Cohesion: 0.24
Nodes (4): Checkpoint, _load_tensors(), _normalisation_from_hf_config(), _normalise_state_dict()

### Community 94 - "Client Evidence Contracts"
Cohesion: 0.29
Nodes (5): Android client evidence appendix (file:line cites at f6e4a0c), friendly()/httpErrorMapping showing detail, Network reliability (HTTP error mapping, retry, cancel, progress, health), Retry resends retained file (vm.retry), WorkManager pending upload queue (UploadWorker)

### Community 96 - "Android README & Schema"
Cohesion: 0.29
Nodes (7): PredictResponse schema (15 legacy keys + request_id, mode), Android README (EYE DETECT AI app), Android stack (Compose, CameraX, Retrofit/OkHttp, Coil), Eye exercises, 20-20-20 reminder, Pomodoro, Result sharing via Intent.ACTION_SEND, 3-screen flow (Patient, Camera, Result), Traffic-light result with confidence and Grad-CAM heatmap

### Community 99 - "Health & API Key Auth"
Cohesion: 0.40
Nodes (5): Agent C: api (main, predict, exams, security, storage), Health endpoints (/health, /live, /ready), X-API-Key authInterceptor, ApiClient.ping() HEAD health check, Backend config via local.properties (API_KEY, API_BASE_URL)

### Community 100 - "download_model.py"
Cohesion: 0.47
Nodes (5): cmd_download(), cmd_verify(), main(), report(), sha256_file()

### Community 101 - "UiState"
Cohesion: 0.25
Nodes (7): Error, Idle, Loading, OfflineSuccess, Queued, Success, UiState

### Community 105 - "get_engine"
Cohesion: 0.29
Nodes (3): get_engine(), UnavailableEngine, test_get_engine_wraps_a_missing_artifact()

### Community 115 - "Backend verify & run (backend/)"
Cohesion: 0.29
Nodes (6): Backend verify & run (backend/), Docker parity (CI job 3), Non-negotiables (from CLAUDE.md §7), One-time environment (Python 3.11), Run locally, The gate (same order as .github/workflows/backend-ci.yml)

### Community 116 - "Models: train → evaluate → ship"
Cohesion: 0.40
Nodes (4): Hard rules, Models: train → evaluate → ship, Pipelines, Serving a real model

### Community 117 - "CLAUDE.md — EYE DETECT AI"
Cohesion: 0.50
Nodes (3): CLAUDE.md — EYE DETECT AI, graphify, Project skills (`.claude/skills/`)

### Community 118 - "Backend ⇄ app wire contract"
Cohesion: 0.50
Nodes (3): Backend ⇄ app wire contract, Checklist for any contract change, Rules

## Knowledge Gaps
- **58 isolated node(s):** `Idle`, `Loading`, `Error`, `Home`, `Patient` (+53 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 713 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **32 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `QualityLevel` connect `Frame Quality Levels` to `Android ViewModel Tests`, `Result Screen UI`, `Camera & Language UI`, `Eye Symmetry Analysis`, `History Screen UI`, `ScreeningViewModel.kt`, `PupilHeuristicsTest`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **What connects `Idle`, `Loading`, `Error` to the rest of the system?**
  _58 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Android ViewModel Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.05524752475247525 - nodes in this community are weakly interconnected._
- **Why does `get_settings()` connect `App Startup & Security` to `Latency Perf Guard`, `Settings`, `Error Envelope Tests`, `Contract Test DB Shim`, `Async Worker & Engine Factory`, `typing`, `Static Serving Integration`, `Non-Fundus Analysis API`, `Predict Endpoint Pipeline`, `get_engine`, `Shared Test Fixtures`, `DR Data Prep & Eval`, `_install_in_memory_crud`, `Exam Persistence Queries`, `test_error_detail_is_string.py`, `Duplicate Retry Tests`, `Route Dependencies & Exams`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Should `test_torch_engine.py` be split into smaller, more focused modules?**
  _Cohesion score 0.11666666666666667 - nodes in this community are weakly interconnected._
- **Why does `upload()` connect `Error Detail Wire Tests` to `test_error_detail_is_string.py`, `Integration Auth Tests`, `Analyze Endpoint Tests`, `Error Envelope Tests`, `Static Serving Integration`, `Contract Auth Tests`, `Predict Contract Tests`, `Static Serving Contract`, `DB Failure Integration`, `Ungradable Wire Tests`, `Engine Spy Safety Test`, `DB Failure Contract Tests`, `Model Unavailable Tests`, `Duplicate Retry Tests`, `Audit Regression Tests`, `Predict Step Failure Tests`?**
  _High betweenness centrality (0.053) - this node is a cross-community bridge._
- **Should `Multi-Analysis Client Flow` be split into smaller, more focused modules?**
  _Cohesion score 0.053551912568306013 - nodes in this community are weakly interconnected._