.PHONY: setup lint scan test

# 1. Setup the local development environment
setup:
	@echo "Installing OS-level dependencies (requires Homebrew)..."
	brew install golangci-lint hadolint yamllint aquasecurity/trivy/trivy || true
	@echo "Setting up Python virtual environment..."
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt
	@echo "Setup complete! Run 'source .venv/bin/activate' to enter the environment."

# 2. Run all code and configuration linters
lint:
	@echo "Linting Python..."
	.venv/bin/flake8 src/api/ src/processor/ --count --select=E9,F63,F7,F82 --show-source --statistics
	@echo "Linting Go..."
	cd src/ingestor && golangci-lint run
	@echo "Linting Kubernetes YAML..."
	yamllint -d "{extends: relaxed, rules: {line-length: disable}}" kubernetes/
	@echo "Linting Dockerfiles..."
	find src -name "Dockerfile" -exec hadolint --ignore DL3018 --ignore DL3008 {} +

# 3. Run local security scans
scan:
	@echo "Scanning Infrastructure as Code..."
	trivy config kubernetes/ --severity CRITICAL,HIGH

# 4. Run local integration tests (against active cluster)
test:
	@echo "Running functional verification..."
	chmod +x tests/*.sh
	./tests/verify_infrastructure.sh
	./tests/verify_application_layer.sh
	./tests/verify_observibility_security.sh