PREFIX := $(HOME)/.meetscribe

.PHONY: build install clean

## Build the Swift helpers (audio capture + OCR) and install them to ~/.meetscribe/bin
build:
	cd audio && swift build -c release
	cd ocr && swift build -c release
	mkdir -p $(PREFIX)/bin
	cp audio/.build/release/audiocap $(PREFIX)/bin/audiocap
	cp ocr/.build/release/ocrtext $(PREFIX)/bin/ocrtext
	@echo "audiocap + ocrtext installed to $(PREFIX)/bin"

## Build the helper and install the Python package + CLI
install: build
	python3 -m pip install .
	@echo
	@echo "Done. Next steps:"
	@echo "  1. export ANTHROPIC_API_KEY=...   (or run 'ant auth login')"
	@echo "  2. meetscribe init"
	@echo "  3. meetscribe record"

clean:
	cd audio && swift package clean
	cd ocr && swift package clean
