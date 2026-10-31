"""categories.py — single source of truth for news categories (fa/en)."""
CATEGORIES_FA = [
    "طراحی محصول", "طراحی صنعتی", "جوایز طراحی", "مسابقات طراحی",
    "همایش‌ها و رویدادها", "آموزش طراحی", "پایداری و محیط زیست",
    "تکنولوژی", "مواد و متریال", "هوش مصنوعی در طراحی",
    "کسب‌وکار", "استارتاپ", "خودرو", "مبلمان",
    "لوازم الکترونیکی", "طراحی پزشکی", "بسته‌بندی", "UX و طراحی خدمات",
    "طراحی جواهرات", "طراحی اکسسوری", "سایر",
]
CATEGORIES_EN = [
    "Product Design", "Industrial Design", "Design Awards", "Design Competitions",
    "Conferences & Events", "Design Education", "Sustainability",
    "Technology", "Materials", "AI in Design", "Business", "Startups",
    "Automotive", "Furniture", "Consumer Electronics", "Medical Design",
    "Packaging", "UX / Service Design", "Jewelry Design", "Accessory Design", "Other",
]
FA_TO_EN = dict(zip(CATEGORIES_FA, CATEGORIES_EN))
EN_TO_FA = dict(zip(CATEGORIES_EN, CATEGORIES_FA))
