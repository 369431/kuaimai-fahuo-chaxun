# -*- coding: utf-8 -*-
"""certinfo.py - 打印 shsp.pw 证书的域名/有效期/链，用于核验。
用法：python certinfo.py
"""
import datetime
import os
import sys

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec, rsa

BASE = os.path.dirname(os.path.abspath(__file__))
CERT_DIR = os.path.join(BASE, "lego", "certificates")
CERT_PATH = os.path.join(CERT_DIR, "shsp.pw.crt")
PRIV_PATH = os.path.join(CERT_DIR, "shsp.pw.key")


def main():
    if not os.path.exists(CERT_PATH):
        print("找不到证书：%s" % CERT_PATH)
        return 1
    with open(CERT_PATH, "rb") as f:
        chain = x509.load_pem_x509_certificates(f.read())
    print("证书文件：%s" % CERT_PATH)
    print("链长度：%d 张" % len(chain))
    for i, c in enumerate(chain):
        try:
            san = [n.value for n in c.extensions.get_extension_for_class(x509.SubjectAlternativeName).value]
        except x509.ExtensionNotFound:
            san = []
        kind = "叶子" if i == 0 else ("根" if i == len(chain) - 1 and c.subject == c.issuer else "中间")
        print("  [%d] %s" % (i, kind))
        print("      subject : %s" % c.subject.rfc4514_string())
        print("      issuer  : %s" % c.issuer.rfc4514_string())
        print("      SAN     : %s" % (", ".join(san) or "-"))
        print("      有效期  : %s ~ %s" % (c.not_valid_before_utc, c.not_valid_after_utc))
    leaf = chain[0]
    pub = leaf.public_key()
    bits = pub.key_size if isinstance(pub, (rsa.RSAPublicKey, ec.EllipticCurvePublicKey)) else "?"
    print("公钥：%s %s 位" % (type(pub).__name__, bits))
    left = leaf.not_valid_after_utc - datetime.datetime.now(datetime.timezone.utc)
    print("剩余天数：%d" % left.days)
    print("私钥存在：%s" % os.path.exists(PRIV_PATH))
    return 0


if __name__ == "__main__":
    sys.exit(main())
