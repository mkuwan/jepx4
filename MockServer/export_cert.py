"""MockServer CA証明書をjepx_projectへエクスポートするスクリプト

dev環境でMockServer CA証明書を使ったTLS検証テストを行う場合に使用。
server.crt を jepx_project/certs/mockserver_ca.pem にコピーする。

使用方法:
  cd MockServer
  python export_cert.py
"""
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SRC = SCRIPT_DIR / 'certs' / 'server.crt'
DEST_DIR = SCRIPT_DIR.parent / 'jepx_project' / 'certs'
DEST = DEST_DIR / 'mockserver_ca.pem'


def main():
    if not SRC.exists():
        print(f"[ERROR] MockServer証明書が見つかりません: {SRC}")
        print("先に MockServer の証明書を生成してください。")
        raise SystemExit(1)

    DEST_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC, DEST)
    print(f"[OK] MockServer CA証明書をエクスポートしました")
    print(f"  FROM: {SRC}")
    print(f"  TO:   {DEST}")
    print()
    print("dev.py の USE_MOCKSERVER_CERT = True で証明書検証付きテストが可能です。")


if __name__ == '__main__':
    main()
