#!/usr/bin/env python3
"""Idempotent App Store Connect deployer using only the REST API and Python stdlib."""
from __future__ import annotations

import argparse, base64, hashlib, json, logging, os, plistlib, random, subprocess, sys, time
import urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

API = "https://api.appstoreconnect.apple.com"
RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504}
PROMOTIONAL_TEXT = "No account, no registration, fully offline — ideal for learning wherever you are."
PROMOTIONAL_TEXT_BY_LOCALE = {
    "ar": "لا حساب، لا تسجيل، يعمل بالكامل دون اتصال بالإنترنت — مثالي للتعلّم أينما كنت.",
    "de": "Kein Konto, keine Registrierung, vollständig offline — ideal zum Lernen, wo immer du bist.",
    "es": "Sin cuenta, sin registro, totalmente sin conexión — ideal para aprender estés donde estés.",
    "fr": "Aucun compte, aucune inscription, entièrement hors ligne — idéal pour apprendre où que vous soyez.",
    "hr": "Bez računa, bez registracije, potpuno izvan mreže — idealno za učenje gdje god bili.",
    "hu": "Nincs fiók, nincs regisztráció, teljesen offline — ideális a tanuláshoz, bárhol is vagy.",
    "it": "Nessun account, nessuna registrazione, completamente offline — ideale per imparare ovunque ti trovi.",
    "ja": "アカウントも登録も不要、完全オフライン。どこにいても学習に最適です。",
    "pl": "Bez konta, bez rejestracji, w pełni offline — idealne do nauki, gdziekolwiek jesteś.",
    "ru": "Без аккаунта, без регистрации, полностью офлайн — идеально для обучения, где бы вы ни были.",
    "tr": "Hesap yok, kayıt yok, tamamen çevrimdışı — nerede olursanız olun öğrenmek için ideal.",
    "uk": "Без облікового запису, без реєстрації, повністю офлайн — ідеально для навчання, де б ви не були.",
    "vi": "Không cần tài khoản, không cần đăng ký, hoàn toàn ngoại tuyến — lý tưởng để học mọi lúc mọi nơi.",
}


def promotional_text(locale: str) -> str:
    """Return the managed promotional text for an App Store locale."""
    return PROMOTIONAL_TEXT_BY_LOCALE.get(locale.split("-", 1)[0].lower(), PROMOTIONAL_TEXT)


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


class DeployError(RuntimeError): pass


class APIRequestError(DeployError):
    """An App Store Connect response that could not be completed."""
    def __init__(self, method: str, url: str, status: Optional[int], response: str):
        self.method, self.url, self.status, self.response = method, url, status, response
        super().__init__(f"{method} {url} failed after retries: " + (f"HTTP {status}: {response[:1200]}" if status else response))

    def unavailable_attribute(self) -> Optional[str]:
        """Return Apple's locked attribute name for a state-error response, if any."""
        if self.status != 409:
            return None
        try:
            errors = json.loads(self.response).get("errors", [])
        except json.JSONDecodeError:
            return None
        for error in errors:
            detail = error.get("detail", "")
            prefix, suffix = "Attribute '", "' cannot be edited at this time"
            if error.get("code") == "STATE_ERROR" and detail.startswith(prefix) and detail.endswith(suffix):
                return detail[len(prefix):-len(suffix)]
        return None

    def duplicate_locale(self) -> bool:
        """Whether Apple says a localization's locale already exists."""
        if self.status != 409:
            return False
        try:
            errors = json.loads(self.response).get("errors", [])
        except json.JSONDecodeError:
            return False
        return any(
            error.get("code") == "ENTITY_ERROR.ATTRIBUTE.INVALID.DUPLICATE"
            and error.get("source", {}).get("pointer") == "/data/attributes/locale"
            for error in errors
        )


class ASC:
    def __init__(self, cfg: Dict[str, Any], dry_run: bool):
        key = cfg["apiKey"]
        self.key_id, self.issuer_id = key["keyId"], key["issuerId"]
        self.key_path = Path(key["privateKeyPath"]).expanduser()
        self.dry_run = dry_run
        self.step_no = 0

    def step(self, title: str) -> None:
        self.step_no += 1
        logging.info("STEP %02d — %s", self.step_no, title)

    def token(self) -> str:
        if not self.key_path.is_file(): raise DeployError(f"API key not found: {self.key_path}")
        header = b64(json.dumps({"alg":"ES256", "kid":self.key_id, "typ":"JWT"}, separators=(",", ":")).encode())
        now = int(time.time())
        claims = b64(json.dumps({"iss":self.issuer_id, "iat":now, "exp":now + 1100, "aud":"appstoreconnect-v1"}, separators=(",", ":")).encode())
        signed = f"{header}.{claims}".encode()
        # openssl creates the required DER ECDSA signature; convert DER to JWT's raw R||S.
        try:
            der = subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(self.key_path)], input=signed, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout
        except FileNotFoundError: raise DeployError("openssl is required to sign the ES256 API token")
        except subprocess.CalledProcessError as e: raise DeployError(f"Could not sign API token: {e.stderr.decode().strip()}")
        if len(der) < 8 or der[0] != 0x30: raise DeployError("openssl returned an invalid ECDSA signature")
        i, length = 2, der[1]
        if length & 0x80: n = length & 0x7f; length = int.from_bytes(der[i:i+n], "big"); i += n
        if der[i] != 2: raise DeployError("invalid ECDSA DER signature")
        rlen = der[i+1]; r = der[i+2:i+2+rlen]; i += 2+rlen
        if der[i] != 2: raise DeployError("invalid ECDSA DER signature")
        slen = der[i+1]; s = der[i+2:i+2+slen]
        raw = int.from_bytes(r, "big").to_bytes(32,"big") + int.from_bytes(s, "big").to_bytes(32,"big")
        return f"{header}.{claims}.{b64(raw)}"

    def request(self, method: str, path: str, body: Optional[Dict[str,Any]]=None, *, raw: Optional[bytes]=None, headers: Optional[Dict[str,str]]=None, allow=(404,)) -> Optional[Dict[str,Any]]:
        url = path if path.startswith("http") else API + path
        payload = raw if raw is not None else (json.dumps(body, separators=(",", ":")).encode() if body is not None else None)
        hdr = dict(headers or {})
        if not url.startswith(API):
            # Apple asset delivery URLs are preauthorized and must not receive the JWT.
            pass
        else:
            hdr["Authorization"] = "Bearer " + self.token()
            hdr.setdefault("Content-Type", "application/json")
            hdr.setdefault("Accept", "application/json")
        last = None
        last_status: Optional[int] = None
        for attempt in range(7):
            try:
                req = urllib.request.Request(url, data=payload, headers=hdr, method=method)
                with urllib.request.urlopen(req, timeout=120) as resp:
                    content = resp.read()
                    return json.loads(content) if content else {}
            except urllib.error.HTTPError as e:
                content = e.read().decode(errors="replace")
                if e.code in allow: return None
                last = f"HTTP {e.code}: {content[:1200]}"
                last_status = e.code
                # Retrying cannot make a field editable.  Surface this precise
                # response immediately so the per-field patcher can skip it.
                state_error = APIRequestError(method, url, e.code, content)
                if state_error.unavailable_attribute() or state_error.duplicate_locale():
                    raise state_error
                retry_after = e.headers.get("Retry-After")
                if e.code not in RETRYABLE: break
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(60, 2 ** attempt + random.random())
            except (urllib.error.URLError, TimeoutError) as e:
                last, delay = str(e), min(60, 2 ** attempt + random.random())
            logging.warning("Request failed (%s); retrying in %.1fs", last, delay)
            time.sleep(delay)
        raise APIRequestError(method, url, last_status, content if last_status else (last or "request failed"))

    def collection(self, path: str) -> List[Dict[str,Any]]:
        out, next_path = [], path
        while next_path:
            page = self.request("GET", next_path, allow=()) or {}
            out.extend(page.get("data", [])); next_path = page.get("links", {}).get("next")
        return out

    def mutate(self, method: str, path: str, body: Dict[str,Any]) -> Dict[str,Any]:
        if self.dry_run:
            logging.info("DRY RUN %s %s", method, path); return {"data":{"id":"dry-run", "type":body.get("data",{}).get("type","")}}
        return self.request(method, path, body, allow=()) or {}

    def mutate_editable_fields(self, path: str, typ: str, ident: str, changed: Dict[str,Any], *, label: str) -> None:
        """Patch independently so a locked optional field does not block other metadata."""
        for field, value in changed.items():
            try:
                self.mutate("PATCH", path, data(typ, {field:value}, ident=ident))
            except APIRequestError as error:
                unavailable = error.unavailable_attribute()
                if unavailable == field:
                    logging.info("Skipping %s.%s because field is not available for edit", label, field)
                    continue
                raise


def data(typ: str, attrs: Optional[Dict[str,Any]]=None, rel: Optional[Dict[str,Any]]=None, ident: Optional[str]=None) -> Dict[str,Any]:
    d: Dict[str,Any] = {"type":typ}
    if ident: d["id"] = ident
    if attrs: d["attributes"] = {k:v for k,v in attrs.items() if v is not None}
    if rel: d["relationships"] = rel
    return {"data":d}

def relationship(typ: str, ident: str) -> Dict[str,Any]: return {"data":{"type":typ,"id":ident}}
def digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()
def checksum(path: Path) -> str: return digest(path, "md5")
def sha256(path: Path) -> str: return digest(path, "sha256")


class Deployer:
    def __init__(self, cfg: Dict[str,Any], root: Path, dry: bool):
        self.cfg, self.api = cfg, ASC(cfg, dry)
        self.root = root.expanduser().resolve()
        if not self.root.is_dir(): raise DeployError(f"deployment root is not a directory: {self.root}")
        self.journal_path = self.root / ".deploy-app-api-state.json"
        self.journal = json.loads(self.journal_path.read_text()) if self.journal_path.exists() else {"assets":{}}
        self.app: Dict[str,Any] = {}

    def save(self) -> None:
        if not self.api.dry_run:
            self.journal_path.write_text(json.dumps(self.journal, indent=2, sort_keys=True) + "\n")
            os.chmod(self.journal_path, 0o600)

    def find(self, path: str, attr: str, value: str) -> Optional[Dict[str,Any]]:
        return next((x for x in self.api.collection(path) if x.get("attributes",{}).get(attr) == value), None)

    def prepare_ipa(self) -> None:
        """Archive and export a signed IPA when the build configuration opts in."""
        build = self.cfg.get("build", {})
        if not build.get("createIpa"): return
        required = ("projectPath", "scheme", "ipaPath")
        missing = [key for key in required if not build.get(key)]
        if missing: raise DeployError(f"build.createIpa requires: {', '.join(missing)}")
        project = Path(build["projectPath"]); project = project if project.is_absolute() else self.root / project
        if not project.exists(): raise DeployError(f"build.projectPath does not exist: {project}")
        ipa = Path(build["ipaPath"]); ipa = ipa if ipa.is_absolute() else self.root / ipa
        archive = Path(build.get("archivePath", "build/App.xcarchive")); archive = archive if archive.is_absolute() else self.root / archive
        export_path = Path(build.get("exportPath", str(ipa.parent))); export_path = export_path if export_path.is_absolute() else self.root / export_path
        options = {"method":"app-store-connect", "destination":"export", "signingStyle":"automatic"}; options.update(build.get("exportOptions", {}))
        self.api.step("archive and export signed IPA with Xcode")
        export_path.mkdir(parents=True, exist_ok=True)
        options_path = export_path / "ExportOptions.plist"; options_path.write_bytes(plistlib.dumps(options, fmt=plistlib.FMT_XML, sort_keys=True))
        archive_command = ["xcodebuild", "archive", "-project", str(project), "-scheme", build["scheme"], "-configuration", build.get("configuration", "Release"), "-destination", "generic/platform=iOS", "-archivePath", str(archive)]
        if build.get("allowProvisioningUpdates"): archive_command.append("-allowProvisioningUpdates")
        try:
            subprocess.run(archive_command, check=True)
            subprocess.run(["xcodebuild", "-exportArchive", "-archivePath", str(archive), "-exportPath", str(export_path), "-exportOptionsPlist", str(options_path)], check=True)
        except FileNotFoundError: raise DeployError("xcodebuild is required to create build.ipaPath")
        except subprocess.CalledProcessError as e: raise DeployError(f"Xcode could not create the signed IPA (exit {e.returncode})")
        if not ipa.is_file():
            exported = sorted(export_path.glob("*.ipa"))
            if len(exported) == 1: exported[0].replace(ipa)
            else: raise DeployError(f"Xcode export did not create the expected IPA: {ipa}")
        logging.info("Created signed IPA: %s", ipa)

    def build_coordinates(self) -> tuple[Dict[str, Any], str, str, str]:
        """Return the configured App Store build identity."""
        build = self.cfg.get("build")
        if not build or not build.get("bundleVersion"):
            raise DeployError("build.bundleVersion is required for an App Store deployment")
        return (
            build,
            str(build.get("shortVersion", self.cfg["version"]["versionString"])),
            str(build["bundleVersion"]),
            str(build.get("platform", self.cfg["version"].get("platform", "IOS"))),
        )

    def uploaded_build(self) -> Optional[Dict[str, Any]]:
        """Find this exact short-version/build-number pair, if Apple has it."""
        _, short, number, platform = self.build_coordinates()
        self.api.step("find matching uploaded build")
        query = urllib.parse.urlencode({
            "filter[app]": self.app["id"],
            "filter[version]": number,
            "include": "preReleaseVersion",
            "limit": "200",
        })
        response = self.api.request("GET", f"/v1/builds?{query}", allow=()) or {}
        prerelease_versions = {item["id"]: item for item in response.get("included", []) if item.get("type") == "preReleaseVersions"}
        for candidate in response.get("data", []):
            if str(candidate.get("attributes", {}).get("version")) != number:
                continue
            prerelease = candidate.get("relationships", {}).get("preReleaseVersion", {}).get("data") or {}
            prerelease_id = prerelease.get("id")
            details = prerelease_versions.get(prerelease_id)
            if details is None and prerelease_id:
                details = (self.api.request("GET", f"/v1/preReleaseVersions/{prerelease_id}", allow=()) or {}).get("data")
            attributes = (details or {}).get("attributes", {})
            if attributes.get("version") == short and attributes.get("platform") == platform:
                logging.info("Reusing uploaded build %s (%s (%s))", candidate["id"], short, number)
                return candidate
        return None

    def ensure_app(self) -> None:
        self.api.step("find existing App Store app record")
        ac = self.cfg["app"]
        self.app = self.find("/v1/apps?limit=200", "bundleId", ac["bundleId"])
        if self.app:
            # App attributes are opt-in: do not overwrite account settings unless named in config.
            wanted = ac.get("attributes", {})
            changed = {k:v for k,v in wanted.items() if self.app.get("attributes",{}).get(k) != v}
            if changed: self.api.mutate_editable_fields(f"/v1/apps/{self.app['id']}", "apps", self.app["id"], changed, label="app")
            logging.info("Reusing app %s", self.app["id"]); return
        raise DeployError("No App Store Connect app record exists for this bundle ID. Apple's current Apps API is read/modify only; create the record once in App Store Connect, then rerun this API-only deployer.")

    def ensure_version(self) -> Dict[str,Any]:
        self.api.step("find or create editable App Store version")
        vc = self.cfg["version"]
        versions = self.api.collection(f"/v1/apps/{self.app['id']}/appStoreVersions?limit=200")
        v = next((x for x in versions if x.get("attributes",{}).get("platform") == vc.get("platform","IOS") and x.get("attributes",{}).get("versionString") == vc["versionString"]), None)
        attrs = {k:vc[k] for k in ("copyright","releaseType","usesIdfa","earliestReleaseDate") if k in vc}
        attrs.update(vc.get("attributes", {}))
        if v:
            state = v.get("attributes", {}).get("appStoreState")
            if state not in ("PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED", "METADATA_REJECTED", "INVALID_BINARY"):
                raise DeployError(f"Version {vc['versionString']} already exists in non-editable state {state}; choose a new versionString")
            if attrs: self.api.mutate_editable_fields(f"/v1/appStoreVersions/{v['id']}", "appStoreVersions", v["id"], attrs, label=f"version {vc['versionString']}")
            return v
        attrs.update({"platform":vc.get("platform","IOS"), "versionString":vc["versionString"]})
        return self.api.mutate("POST", "/v1/appStoreVersions", data("appStoreVersions", attrs, {"app":relationship("apps",self.app["id"])}))["data"]

    def locales(self) -> Dict[str,Any]:
        path = Path(self.cfg.get("localizationsPath", "localizations.json")); path = path if path.is_absolute() else self.root/path
        if not path.is_file(): raise DeployError(f"localizations.json not found: {path}")
        loaded = json.loads(path.read_text())
        if not isinstance(loaded, dict) or not loaded: raise DeployError("localizations.json must be a non-empty locale object")
        return loaded

    def upsert_localizations(self, version: Dict[str,Any], locales: Dict[str,Any]) -> Dict[str,Dict[str,Any]]:
        self.api.step("synchronize app-info and version localizations")
        app_infos = self.api.collection(f"/v1/apps/{self.app['id']}/appInfos?limit=200")
        if not app_infos:
            raise DeployError(f"App {self.app['id']} has no App Info resource")
        app_info = app_infos[0]
        old_info = self.api.collection(f"/v1/appInfos/{app_info['id']}/appInfoLocalizations?limit=200")
        old_ver = self.api.collection(f"/v1/appStoreVersions/{version['id']}/appStoreVersionLocalizations?limit=200")
        result = {}
        for locale, source in locales.items():
            ai = source.get("appInformation", {})
            av = source.get("appStoreVersion", source.get("appInformation", {}))
            info_attrs = {"locale":locale, **{k:ai[k] for k in ("name","subtitle","privacyPolicyUrl") if k in ai}}
            ver_attrs = {"locale":locale, **{k:av[k] for k in ("description","keywords","marketingUrl","supportUrl","whatsNew") if k in av}}
            # Keep the store listing's message consistent across every app.
            # This deliberately overrides stale values in localizations.json.
            ver_attrs["promotionalText"] = promotional_text(locale)
            if not info_attrs.get("name"): raise DeployError(f"{locale}: appInformation.name is required")
            existing = next((x for x in old_info if x.get("attributes",{}).get("locale")==locale), None)
            if existing:
                changed = {k:v for k,v in info_attrs.items() if existing.get("attributes",{}).get(k)!=v}
                if changed: self.api.mutate_editable_fields(f"/v1/appInfoLocalizations/{existing['id']}", "appInfoLocalizations", existing["id"], changed, label=f"{locale} app-information localization")
            else:
                try:
                    self.api.mutate("POST", "/v1/appInfoLocalizations", data("appInfoLocalizations", info_attrs, {"appInfo":relationship("appInfos", app_info["id"])}))
                except APIRequestError as error:
                    if not error.duplicate_locale(): raise
                    logging.info("Locale %s already exists for app information; refreshing and updating it", locale)
                    existing = next((x for x in self.api.collection(f"/v1/appInfos/{app_info['id']}/appInfoLocalizations?limit=200") if x.get("attributes",{}).get("locale") == locale), None)
                    if not existing: raise DeployError(f"{locale}: Apple reported a duplicate app-information localization but did not return it")
                    changed = {k:v for k,v in info_attrs.items() if existing.get("attributes",{}).get(k) != v}
                    if changed: self.api.mutate_editable_fields(f"/v1/appInfoLocalizations/{existing['id']}", "appInfoLocalizations", existing["id"], changed, label=f"{locale} app-information localization")
            existing = next((x for x in old_ver if x.get("attributes",{}).get("locale")==locale), None)
            if existing:
                changed = {k:v for k,v in ver_attrs.items() if existing.get("attributes",{}).get(k)!=v}
                if changed: self.api.mutate_editable_fields(f"/v1/appStoreVersionLocalizations/{existing['id']}", "appStoreVersionLocalizations", existing["id"], changed, label=f"{locale} version localization")
                result[locale]=existing
            else:
                try:
                    result[locale] = self.api.mutate("POST", "/v1/appStoreVersionLocalizations", data("appStoreVersionLocalizations", ver_attrs, {"appStoreVersion":relationship("appStoreVersions", version["id"])}))["data"]
                except APIRequestError as error:
                    if not error.duplicate_locale(): raise
                    logging.info("Locale %s already exists for version metadata; refreshing and updating it", locale)
                    existing = next((x for x in self.api.collection(f"/v1/appStoreVersions/{version['id']}/appStoreVersionLocalizations?limit=200") if x.get("attributes",{}).get("locale") == locale), None)
                    if not existing: raise DeployError(f"{locale}: Apple reported a duplicate version localization but did not return it")
                    changed = {k:v for k,v in ver_attrs.items() if existing.get("attributes",{}).get(k) != v}
                    if changed: self.api.mutate_editable_fields(f"/v1/appStoreVersionLocalizations/{existing['id']}", "appStoreVersionLocalizations", existing["id"], changed, label=f"{locale} version localization")
                    result[locale] = existing
        return result

    def ensure_set(self, localization: Dict[str,Any], kind: str, display: str) -> Dict[str,Any]:
        route = "appScreenshotSets" if kind == "screenshot" else "appPreviewSets"
        field = "screenshotDisplayType" if kind == "screenshot" else "previewType"
        existing = self.api.collection(f"/v1/appStoreVersionLocalizations/{localization['id']}/{route}?limit=200")
        found = next((x for x in existing if x.get("attributes",{}).get(field)==display), None)
        if found: return found
        return self.api.mutate("POST", f"/v1/{route}", data(route, {field:display}, {"appStoreVersionLocalization":relationship("appStoreVersionLocalizations",localization["id"])}))["data"]

    def upload_asset(self, set_id: str, kind: str, file: Path) -> None:
        if not file.is_file(): raise DeployError(f"asset does not exist: {file}")
        route, typ, rel = ("appScreenshots","appScreenshots","appScreenshotSet") if kind=="screenshot" else ("appPreviews","appPreviews","appPreviewSet")
        key = f"{kind}:{set_id}:{sha256(file)}"
        existing = self.api.collection(f"/v1/{'appScreenshotSets' if kind=='screenshot' else 'appPreviewSets'}/{set_id}/{route}?limit=200")
        # Filename+size avoids duplicate asset reservations; Apple's checksum is not always returned.
        if any(x.get("attributes",{}).get("fileName")==file.name and x.get("attributes",{}).get("fileSize")==file.stat().st_size for x in existing):
            logging.info("Asset already exists: %s", file.name); return
        reservation_id = self.journal["assets"].get(key)
        asset = self.api.request("GET", f"/v1/{route}/{reservation_id}") if reservation_id else None
        if not asset or asset.get("data",{}).get("attributes",{}).get("assetDeliveryState",{}).get("state") in ("FAILED","COMPLETE"):
            asset = self.api.mutate("POST",f"/v1/{route}",data(typ,{"fileName":file.name,"fileSize":file.stat().st_size},{rel:relationship("appScreenshotSets" if kind=="screenshot" else "appPreviewSets",set_id)}))
            reservation_id=asset["data"]["id"]; self.journal["assets"][key]=reservation_id; self.save()
        resource=asset["data"]; attrs=resource.get("attributes",{})
        if not self.api.dry_run and not attrs.get("uploaded"):
            with file.open("rb") as fh:
                for op in attrs.get("uploadOperations",[]):
                    fh.seek(op["offset"]); chunk=fh.read(op["length"])
                    self.api.request(op["method"],op["url"],raw=chunk,headers={h["name"]:h["value"] for h in op.get("requestHeaders",[])},allow=())
            self.api.mutate("PATCH",f"/v1/{route}/{reservation_id}",data(typ,{"uploaded":True,"sourceFileChecksum":checksum(file)},ident=reservation_id))
        logging.info("Uploaded %s %s", kind, file.name)

    def media(self, localizations: Dict[str,Dict[str,Any]]) -> None:
        media = self.cfg.get("media", {})
        self.api.step("upload missing screenshots and previews")
        for kind, plural in (("screenshot","screenshots"),("preview","previews")):
            for spec in media.get(plural, []):
                locale, display = spec["locale"], spec["displayType"]
                if locale not in localizations: raise DeployError(f"media locale {locale} has no version localization")
                aset=self.ensure_set(localizations[locale],kind,display)
                # A per-device folder is the conventional layout.  Keep an
                # explicit folder available for uncommon asset layouts.
                specified_files = spec.get("files")
                if specified_files is not None:
                    if not isinstance(specified_files, list) or not specified_files:
                        raise DeployError(f"{kind} media files must be a non-empty list")
                    paths=[]
                    for raw_file in specified_files:
                        file=Path(raw_file); file=file if file.is_absolute() else self.root/file
                        if not file.is_file(): raise DeployError(f"{kind} media file does not exist: {file}")
                        paths.append(file)
                    paths=sorted(paths)
                    media_source="explicit media files"
                else:
                    raw_folder = spec.get("folder", f"{plural}/{locale}/{display}")
                    folder=Path(raw_folder); folder=folder if folder.is_absolute() else self.root/folder
                    if not folder.is_dir(): raise DeployError(f"{kind} media folder does not exist: {folder}")
                    paths=sorted(path for path in folder.rglob("*") if path.is_file() and not any(part.startswith(".") for part in path.relative_to(folder).parts))
                    media_source=str(folder)
                if not paths: raise DeployError(f"{kind} media source contains no files: {media_source}")
                for path in paths:
                    self.upload_asset(aset["id"],kind,path)

    def ensure_products(self, locales: Dict[str,Any]) -> None:
        purchases = self.cfg.get("purchases", {})
        self.api.step("create/reuse subscriptions, in-app purchases, prices, and localizations")
        groups=self.api.collection(f"/v1/apps/{self.app['id']}/subscriptionGroups?limit=200")
        for g in purchases.get("subscriptionGroups",[]):
            group=next((x for x in groups if x.get("attributes",{}).get("referenceName")==g["referenceName"]),None)
            if not group: group=self.api.mutate("POST","/v1/subscriptionGroups",data("subscriptionGroups",{"referenceName":g["referenceName"]},{"app":relationship("apps",self.app["id"])}))["data"]
            subs=self.api.collection(f"/v1/subscriptionGroups/{group['id']}/subscriptions?limit=200")
            for p in g.get("subscriptions",[]):
                product=next((x for x in subs if x.get("attributes",{}).get("productId")==p["productId"]),None)
                if not product:
                    attrs={k:p[k] for k in ("name","productId","subscriptionPeriod","familySharable") if k in p}
                    product=self.api.mutate("POST","/v1/subscriptions",data("subscriptions",attrs,{"group":relationship("subscriptionGroups",group["id"])}))["data"]
                self.product_version_locales(product,"subscription",locales)
                self.subscription_price(product,p)
        # Apple intentionally does not expose a GET_COLLECTION operation for
        # /v2/inAppPurchases.  IAPs must instead be listed through the app's
        # v1 relationship endpoint; use v2 only for individual IAP resources.
        all_iap=self.api.collection(f"/v1/apps/{self.app['id']}/inAppPurchasesV2?limit=200")
        for p in purchases.get("inAppPurchases",[]):
            product=next((x for x in all_iap if x.get("attributes",{}).get("productId")==p["productId"]),None)
            if not product:
                attrs={k:p[k] for k in ("name","productId","inAppPurchaseType","familySharable","reviewNote") if k in p}
                product=self.api.mutate("POST","/v2/inAppPurchases",data("inAppPurchases",attrs,{"app":relationship("apps",self.app["id"])}))["data"]
            self.product_version_locales(product,"iap",locales); self.iap_price(product,p)

    def product_version_locales(self, product: Dict[str,Any], kind: str, locales: Dict[str,Any]) -> None:
        version_type="subscriptionVersions" if kind=="subscription" else "inAppPurchaseVersions"
        parent="/v1/subscriptions" if kind=="subscription" else "/v2/inAppPurchases"
        versions=self.api.collection(f"{parent}/{product['id']}/versions?limit=200")
        version=next((x for x in versions if x.get("attributes",{}).get("state")=="PREPARE_FOR_SUBMISSION"),None)
        if not version:
            rel="subscription" if kind=="subscription" else "inAppPurchase"
            version=self.api.mutate("POST",f"/v1/{version_type}",data(version_type,rel={rel:relationship("subscriptions" if kind=="subscription" else "inAppPurchases",product["id"])}))["data"]
        old=self.api.collection(f"/v1/{version_type}/{version['id']}/localizations?limit=200")
        typ="subscriptionLocalizations" if kind=="subscription" else "inAppPurchaseLocalizations"
        pid=product.get("attributes",{}).get("productId")
        for locale, source in locales.items():
            src=source.get("subscriptions",{}).get(pid) or source.get("inAppPurchases",{}).get(pid)
            if not src: continue
            attrs={"locale":locale,"name":src.get("displayName",src.get("name")),"description":src.get("description")}
            if not attrs["name"] or not attrs["description"]: raise DeployError(f"{locale}: localization for {pid} needs displayName and description")
            current=next((x for x in old if x.get("attributes",{}).get("locale")==locale),None)
            if current:
                changed={k:v for k,v in attrs.items() if current.get("attributes",{}).get(k)!=v}
                if changed:self.api.mutate_editable_fields(f"/v2/{typ}/{current['id']}", typ, current["id"], changed, label=f"{locale} {pid} localization")
            else:
                try:
                    self.api.mutate("POST", f"/v2/{typ}", data(typ, attrs, {"version":relationship(version_type, version["id"])}))
                except APIRequestError as error:
                    if not error.duplicate_locale(): raise
                    logging.info("Locale %s already exists for %s; refreshing and updating it", locale, pid)
                    current = next((x for x in self.api.collection(f"/v1/{version_type}/{version['id']}/localizations?limit=200") if x.get("attributes",{}).get("locale") == locale), None)
                    if not current: raise DeployError(f"{locale}: Apple reported a duplicate {pid} localization but did not return it")
                    changed = {k:v for k,v in attrs.items() if current.get("attributes",{}).get(k) != v}
                    if changed:self.api.mutate_editable_fields(f"/v2/{typ}/{current['id']}", typ, current["id"], changed, label=f"{locale} {pid} localization")

    def price_point(self,path:str,price:float)->Dict[str,Any]:
        return next((x for x in self.api.collection(path) if float(x.get("attributes",{}).get("customerPrice",-1))==float(price)), None) or (_ for _ in ()).throw(DeployError(f"No USA price point for {price}"))
    def subscription_price(self,product:Dict[str,Any],p:Dict[str,Any])->None:
        if "price" not in p:return
        existing=self.api.collection(f"/v1/subscriptions/{product['id']}/prices?filter[territory]=USA&filter[planType]=UPFRONT&limit=200")
        if existing:return
        plans=self.api.collection(f"/v1/subscriptions/{product['id']}/planAvailabilities?limit=200")
        if not any(x.get("attributes",{}).get("planType")=="UPFRONT" for x in plans): self.api.mutate("POST","/v1/subscriptionPlanAvailabilities",data("subscriptionPlanAvailabilities",{"planType":"UPFRONT","availableInNewTerritories":False},{"subscription":relationship("subscriptions",product["id"]),"availableTerritories":{"data":[{"type":"territories","id":"USA"}]}}))
        point=self.price_point(f"/v1/subscriptions/{product['id']}/pricePoints?filter[territory]=USA&filter[planType]=UPFRONT&limit=200",p["price"])
        self.api.mutate("POST","/v1/subscriptionPrices",data("subscriptionPrices",{"planType":"UPFRONT"},{"subscription":relationship("subscriptions",product["id"]),"subscriptionPricePoint":relationship("subscriptionPricePoints",point["id"])}))
    def iap_price(self,product:Dict[str,Any],p:Dict[str,Any])->None:
        if "price" not in p:return
        if self.api.request("GET",f"/v2/inAppPurchases/{product['id']}/relationships/iapPriceSchedule") is not None:return
        point=self.price_point(f"/v2/inAppPurchases/{product['id']}/pricePoints?filter[territory]=USA&limit=200",p["price"]); temp="${price1}"
        body=data("inAppPurchasePriceSchedules",rel={"inAppPurchase":relationship("inAppPurchases",product["id"]),"baseTerritory":relationship("territories","USA"),"manualPrices":{"data":[{"type":"inAppPurchasePrices","id":temp}]}}); body["included"]=[{"type":"inAppPurchasePrices","id":temp,"attributes":{},"relationships":{"inAppPurchaseV2":relationship("inAppPurchases",product["id"]),"inAppPurchasePricePoint":relationship("inAppPurchasePricePoints",point["id"])}}]
        self.api.mutate("POST","/v1/inAppPurchasePriceSchedules",body)

    def wait_for_valid_build_and_attach(self, version: Dict[str,Any], build_id: str, timeout: int) -> None:
        """Wait for Apple's validation, then associate the build with the version."""
        deadline=time.monotonic()+timeout
        self.api.step("wait for build validation and attach it to version")
        while time.monotonic() < deadline:
            resource=(self.api.request("GET",f"/v1/builds/{build_id}",allow=()) or {}).get("data",{})
            state=resource.get("attributes",{}).get("processingState")
            if state == "VALID":
                self.api.mutate("PATCH",f"/v1/appStoreVersions/{version['id']}/relationships/build",{"data":{"type":"builds","id":build_id}})
                return
            if state == "INVALID": raise DeployError(f"Apple marked build {build_id} invalid")
            time.sleep(15)
        raise DeployError("Timed out waiting for Apple build validation; rerun safely later")

    def upload_build(self, version: Dict[str,Any], existing_build: Optional[Dict[str,Any]]=None) -> None:
        """Use Apple's Build Upload REST workflow; no Transporter or Fastlane involved."""
        build, short, number, platform = self.build_coordinates()
        if existing_build:
            self.wait_for_valid_build_and_attach(version, existing_build["id"], int(build.get("processingTimeoutSeconds",1800)))
            return
        ipa = Path(build["ipaPath"]); ipa = ipa if ipa.is_absolute() else self.root / ipa
        if not ipa.is_file() or ipa.suffix.lower() != ".ipa": raise DeployError(f"build.ipaPath must name an existing .ipa: {ipa}")
        self.api.step("find or create API build upload")
        query = urllib.parse.urlencode({"filter[cfBundleShortVersionString]":short,"filter[cfBundleVersion]":number,"filter[platform]":platform,"limit":"200"})
        uploads = self.api.collection(f"/v1/apps/{self.app['id']}/buildUploads?{query}")
        upload = next((x for x in uploads if x.get("attributes",{}).get("state",{}).get("state") not in ("FAILED","EXPIRED")), None)
        if not upload:
            upload=self.api.mutate("POST","/v1/buildUploads",data("buildUploads",{"cfBundleShortVersionString":short,"cfBundleVersion":number,"platform":platform},{"app":relationship("apps",self.app["id"])}))["data"]
            self.journal["buildUploadId"] = upload["id"]; self.save()
        if self.api.dry_run: return
        upload_id=upload["id"]
        files=self.api.collection(f"/v1/buildUploads/{upload_id}/buildUploadFiles?limit=200")
        item=next((x for x in files if x.get("attributes",{}).get("fileName")==ipa.name and x.get("attributes",{}).get("fileSize")==ipa.stat().st_size),None)
        if not item:
            self.api.step("reserve IPA upload file")
            item=self.api.mutate("POST","/v1/buildUploadFiles",data("buildUploadFiles",{"fileName":ipa.name,"fileSize":ipa.stat().st_size,"assetType":"ASSET","uti":"com.apple.ipa"},{"buildUpload":relationship("buildUploads",upload_id)}))["data"]
        attrs=item.get("attributes",{})
        state=attrs.get("assetDeliveryState",{}).get("state")
        if state not in ("COMPLETE","UPLOAD_COMPLETE"):
            self.api.step("upload IPA chunks")
            with ipa.open("rb") as source:
                for operation in attrs.get("uploadOperations",[]):
                    source.seek(operation["offset"]); part=source.read(operation["length"])
                    self.api.request(operation["method"],operation["url"],raw=part,headers={x["name"]:x["value"] for x in operation.get("requestHeaders",[])},allow=())
            checksums={"file":{"hash":sha256(ipa),"algorithm":"SHA_256"},"composite":{"hash":checksum(ipa),"algorithm":"MD5"}}
            self.api.mutate("PATCH",f"/v1/buildUploadFiles/{item['id']}",data("buildUploadFiles",{"uploaded":True,"sourceFileChecksums":checksums},ident=item["id"]))
        self.api.step("wait for build upload processing")
        deadline=time.monotonic()+int(build.get("processingTimeoutSeconds",1800))
        build_id=None
        while time.monotonic() < deadline:
            current=self.api.request("GET",f"/v1/buildUploads/{upload_id}?include=build",allow=()) or {}
            resource=current.get("data",{}); state=resource.get("attributes",{}).get("state",{}).get("state")
            if state == "FAILED": raise DeployError(f"Apple rejected build upload: {resource.get('attributes',{}).get('state',{})}")
            rel=resource.get("relationships",{}).get("build",{}).get("data")
            if rel: build_id=rel["id"]; break
            time.sleep(15)
        if not build_id: raise DeployError("Timed out waiting for Apple to create the Build resource; rerun safely later")
        self.wait_for_valid_build_and_attach(version, build_id, max(0, int(deadline - time.monotonic())))

    def run(self) -> None:
        self.ensure_app(); existing_build=self.uploaded_build()
        if existing_build is None: self.prepare_ipa()
        version=self.ensure_version(); locales=self.locales(); version_locales=self.upsert_localizations(version,locales); self.media(version_locales); self.ensure_products(locales); self.upload_build(version, existing_build); self.save()
        self.api.step("deployment API reconciliation complete")


EXAMPLE={"apiKey":{"keyId":"ABC123DEFG","issuerId":"00000000-0000-0000-0000-000000000000","privateKeyPath":"/secure/path/AuthKey_ABC123DEFG.p8"},"app":{"bundleId":"com.example.app","sku":"example-app","primaryLocale":"en-US"},"version":{"platform":"IOS","versionString":"1.0","releaseType":"MANUAL","usesIdfa":False,"copyright":"2026 Example"},"build":{"ipaPath":"build/Example.ipa","bundleVersion":"1","processingTimeoutSeconds":1800},"localizationsPath":"localizations.json","media":{"screenshots":[{"locale":"en-US","displayType":"APP_IPHONE_67"}],"previews":[]},"purchases":{"subscriptionGroups":[],"inAppPurchases":[]}}
def main()->None:
    default_config = Path(__file__).resolve().with_name("deployment.json")
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("root", nargs="?", help="required app-assets root directory"); p.add_argument("--config", default=str(default_config), help=f"configuration file (default: {default_config})"); p.add_argument("--dry-run",action="store_true"); p.add_argument("--build-only",action="store_true",help="create the configured IPA without contacting App Store Connect"); p.add_argument("--write-example",metavar="PATH"); args=p.parse_args()
    if args.write_example: Path(args.write_example).write_text(json.dumps(EXAMPLE,indent=2)+"\n"); return
    if not args.root:p.error("root is required")
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    try:
        deployer=Deployer(json.loads(Path(args.config).read_text()),Path(args.root),args.dry_run)
        deployer.prepare_ipa() if args.build_only else deployer.run()
    except (DeployError,KeyError,ValueError,json.JSONDecodeError) as e: logging.error("Deployment stopped: %s",e); sys.exit(1)
if __name__=="__main__": main()
