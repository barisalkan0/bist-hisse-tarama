"""
"Planları Gör" linki üretimi.

Gerçek Lemon Squeezy checkout akışı (3 katman × aylık/yıllık = 6 varyant) artık
valysera-web'in `/pricing` sayfasında yaşıyor — orada zaten güzel tasarlanmış bir
karşılaştırma tablosu var, checkout linklerini burada tekrarlamak yerine kullanıcıyı
oraya, kimliğini (email + user_id) query param olarak taşıyarak yönlendiriyoruz.
valysera `/pricing` sayfası bu paramları okuyup her checkout linkine
`checkout[custom][user_id]` / `checkout[email]` olarak ekler.
"""
from urllib.parse import urlencode

PRICING_URL = "https://valysera.com/pricing"


def pricing_url(email: str | None = None, user_id: str | None = None) -> str:
    """valysera.com/pricing linki; varsa email/user_id query param olarak eklenir."""
    params = {}
    if user_id:
        params["uid"] = user_id
    if email:
        params["email"] = email
    return f"{PRICING_URL}?{urlencode(params)}" if params else PRICING_URL
