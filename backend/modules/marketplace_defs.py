"""Shared marketplace forums, categories, and contract status definitions."""

MARKET_FORUMS: dict[int, str] = {
    163: "Marketplace Discussions", 402: "Promotional Advertising",
    186: "Free Services and Giveaways", 205: "Appraisals and Pricing",
    217: "Jobs and Partnerships", 111: "Deal Disputes",
    107: "Premium Sellers Section", 374: "Premium Tools and Programs",
    299: "Cryptography and Encryption Market", 136: "Ebook Bazaar",
    182: "Currency Exchange", 218: "Virtual Game Items",
    145: "Hosting Services", 263: "Social Media Services",
    106: "Service Offerings", 219: "Graphics Market",
    171: "VPN and Proxy Services", 308: "Service Requests",
    44: "Buyers Bay", 176: "Member Sales Market",
    291: "Online Accounts", 404: "Marketplace Miscellaneous",
    339: "Hash Bounties", 255: "Rewards and Small Favors",
    225: "Webmaster Marketplace",
}

MARKET_CATEGORIES = (
    ("hosting", "Hosting"), ("social", "Social Media"),
    ("accounts", "Online Accounts"), ("design", "Graphics & Design"),
    ("development", "Development"), ("security", "Security"),
    ("crypto", "Crypto & Exchange"), ("gaming", "Gaming"),
    ("marketing", "Marketing"), ("data", "Data & Research"),
    ("other", "Other"),
)

CONTRACT_STATUSES = {
    "0": "awaiting", "1": "awaiting", "2": "cancelled",
    "3": "middleman", "4": "cancelled", "5": "active",
    "6": "complete", "7": "disputed", "8": "expired",
}

BUYER_FORUMS = frozenset({44, 308, 339})
DISPUTE_FORUMS = frozenset({111})
