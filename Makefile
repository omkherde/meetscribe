PREFIX := $(HOME)/.meetscribe

.PHONY: build install clean

## Build the Swift system-audio capture helper and install it to ~/.meetscribe/bin
build:
	cd audio && swift build -c release
	mkdir -p $(PREFIX)/bin
	cp audio/.build/release/audiocap $(PREFIX)/bin/audiocap
	@echo "audiocap installed to $(PREFIX)/bin/audiocap"

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
