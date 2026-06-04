#!/usr/bin/env python3
"""Basic route and API smoke QA for marketing dashboard."""

import os
import re
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
db_path = project_root / "data" / "marketing_dashboard.db"
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
os.environ.setdefault("DASHBOARD_SECRET_KEY", "test")

from dashboard.app import app


def _normalize_path(route: str) -> str:
    path = route
    path = re.sub(r"<int:[^>]+>", "1", path)
    path = re.sub(r"<string:[^>]+>", "test", path)
    path = re.sub(r"<[^>]+>", "test", path)
    return path


def main() -> None:
    get_ok = get_redirect = get_error = 0
    api_2xx = api_3xx = api_4xx = api_5xx = 0
    bad_get = []
    bad_api = []
    brand_dropdown_count = 0
    active_brand_value = ""

    with app.test_client() as client:
        # Verify AI generation brand dropdown is populated from user_brands context.
        try:
            html = client.get("/generate", follow_redirects=False).get_data(as_text=True)
            brand_select_match = re.search(r"<label[^>]*>Brand</label>\s*<select[^>]*>(.*?)</select>", html, re.DOTALL)
            if brand_select_match:
                brand_options_html = brand_select_match.group(1)
                option_values = re.findall(r'<option\s+value="([^"]+)"[^>]*>', brand_options_html)
                brand_dropdown_count = len([v for v in option_values if v.strip()])
            active_match = re.search(r"const ACTIVE_BRAND =\s*([\"'][^\"']*[\"'])", html)
            active_brand_value = active_match.group(1) if active_match else ""
        except Exception:
            pass

        for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
            route = rule.rule
            if route.startswith("/static/"):
                continue

            methods = set(rule.methods or [])
            test_path = _normalize_path(route)

            if "GET" in methods:
                try:
                    code = client.get(test_path, follow_redirects=False).status_code
                except Exception as exc:
                    code = "EXC"
                    bad_get.append((route, test_path, str(exc)))

                if code == "EXC":
                    get_error += 1
                elif code >= 400:
                    get_error += 1
                    bad_get.append((route, test_path, code))
                elif code >= 300:
                    get_redirect += 1
                else:
                    get_ok += 1

            write_methods = methods.intersection({"POST", "PUT", "PATCH", "DELETE"})
            if write_methods and route.startswith("/api/"):
                method = sorted(write_methods)[0]
                kwargs = {"follow_redirects": False}
                if method in {"POST", "PUT", "PATCH"}:
                    kwargs["json"] = {}

                try:
                    code = client.open(test_path, method=method, **kwargs).status_code
                except Exception as exc:
                    code = "EXC"
                    bad_api.append((route, method, test_path, str(exc)))

                if code == "EXC":
                    api_5xx += 1
                elif code >= 500:
                    api_5xx += 1
                    bad_api.append((route, method, test_path, code))
                elif code >= 400:
                    api_4xx += 1
                elif code >= 300:
                    api_3xx += 1
                else:
                    api_2xx += 1

    print(f"GET ok={get_ok} redirect={get_redirect} error={get_error}")
    print(f"API write 2xx={api_2xx} 3xx={api_3xx} 4xx={api_4xx} 5xx={api_5xx}")
    print(f"GENERATE_BRAND_OPTIONS={brand_dropdown_count}")
    print(f"ACTIVE_BRAND_JS={active_brand_value}")
    print("BAD GET (first 20):")
    for row in bad_get[:20]:
        print(row)
    print("BAD API 5xx/EXC (first 20):")
    for row in bad_api[:20]:
        print(row)


if __name__ == "__main__":
    main()
