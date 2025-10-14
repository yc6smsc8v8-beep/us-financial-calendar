CMD ["sh", "-c", "gunicorn app_combined_safe:app --bind 0.0.0.0:${PORT:-5000} --workers 1 --timeout 120"]

