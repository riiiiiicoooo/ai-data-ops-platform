{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.postgresql_15
    pkgs.redis
    pkgs.git
    pkgs.gcc
    pkgs.pkg-config
    pkgs.libpq
  ];

  env = {
    PYTHON_VERSION = "3.11";
    PYTHONPATH = "/home/runner/work:${pkgs.python311.libPrefix}";
    PIP_CACHE_DIR = "/home/runner/.cache/pip";
  };

  postInit = ''
    # Initialize PostgreSQL
    pg_ctl initdb -D /home/runner/pgdata || true

    # Install Python dependencies
    pip install --upgrade pip
    pip install -r requirements.txt

    echo "✓ PostgreSQL 15, Redis, and Python 3.11 ready"
    echo "✓ Dependencies installed from requirements.txt"
    echo ""
    echo "Quick start:"
    echo "  make setup       # Full setup"
    echo "  python demo/run_demo.py  # Run demo"
    echo "  pytest tests/ -v # Run tests"
  '';
}
