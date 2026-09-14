.PHONY: assets check build
assets:
	python3 tools/extract_visual_sheet.py
	python3 tools/render_runtime_preview.py
check:
	python3 tests/source_checks.py
	./tests/host_syntax.sh
build: check
	./build.sh
