.PHONY: assets check build screens capture
assets:
	python3 tools/generate_assets.py
	python3 tools/generate_audio.py
check:
	python3 tests/source_checks.py
	./tests/host_syntax.sh
	./tests/run_harness.sh
build:
	./build.sh
screens:
	python3 tools/render_screens.py
capture:
	python3 tools/qemu_capture.py
