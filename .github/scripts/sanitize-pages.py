from pathlib import Path

path = Path("frontend/index.html")
text = path.read_text(encoding="utf-8")

# Never publish accidental JavaScript/text appended after the HTML document.
end = text.lower().rfind("</html>")
if end == -1:
    raise SystemExit("frontend/index.html has no closing </html>")
text = text[:end + len("</html>")] + "\n"

# Remove legacy boot text if an older repair ever left it inside the document.
legacy = "// Boot the data dashboard even when Cesium is unavailable."
if legacy in text:
    text = text.replace(legacy, "")

path.write_text(text, encoding="utf-8")
print("Pages HTML sanitized")
