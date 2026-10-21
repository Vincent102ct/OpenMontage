"""Closed vocabularies for rule-based story analysis (Vietnamese and English).

This is the only source file that contains Vietnamese text: it is linguistic data the
analyzer needs to read Vietnamese stories, not messages, identifiers or comments.

Data only. Every label the analyzer or a local LLM may emit must come from the
enums here, so the planner never sees free-form actions it cannot animate.
Phrases are matched longest-first on word boundaries in lowercased text.
"""
from __future__ import annotations

# Animatable action vocabulary (planner implements each one).
ACTIONS = [
    "idle", "walk", "approach", "run", "enter", "exit", "sit", "stand_up", "look",
    "pick_up", "hold", "put_down", "give", "open", "close", "knock", "talk", "wave",
    "point", "nod", "shake_head", "smile", "sad", "surprise", "fear", "think", "read",
    "operate", "lights_on", "lights_off", "dress", "sleep", "board", "vehicle_arrive",
    "reveal", "disappear",
]

LOCATION_KINDS = ["office", "street", "living_room", "kitchen", "shop", "bedroom", "park", "room"]
OUTDOOR_KINDS = {"street", "park"}

PROP_KINDS = [
    "umbrella", "bag", "phone", "letter", "book", "newspaper", "cup", "bread", "coin",
    "key", "box", "bottle", "tray", "flower", "bus", "car",
]
VEHICLE_KINDS = {"bus", "car"}

# Fixed location features an action may target (anchors in tools/story/locations.py).
FEATURES = ["door", "window", "seat", "table", "shelf", "corner", "oven", "computer", "bed", "counter", "light"]

LOCATION_WORDS = {
    "vi": {
        "office": ["văn phòng", "công ty", "phòng làm việc", "cơ quan"],
        "street": ["trạm xe buýt", "bến xe buýt", "bến xe", "ngoài đường", "ra đường", "con đường", "đường phố",
                   "vỉa hè", "con hẻm", "con ngõ", "phố", "đường", "hẻm", "ngõ"],
        "living_room": ["phòng khách", "về đến nhà", "về nhà", "ở nhà", "căn nhà", "căn hộ"],
        "kitchen": ["nhà bếp", "căn bếp", "gian bếp", "bếp"],
        "shop": ["tiệm bánh", "cửa hàng", "cửa tiệm", "quán cà phê", "quán", "tiệm", "chợ"],
        "bedroom": ["phòng ngủ", "giường"],
        "park": ["công viên", "khu vườn", "rừng", "vườn", "bờ hồ"],
        "room": ["lớp học", "phòng học", "hành lang", "căn phòng"],
    },
    "en": {
        "office": ["office", "workplace", "company"],
        "street": ["bus stop", "the street", "street", "road", "sidewalk", "alley", "crossroads", "corner of"],
        "living_room": ["living room", "lounge", "came home", "got home", "at home", "apartment", "flat"],
        "kitchen": ["kitchen"],
        "shop": ["bakery", "shop", "store", "café", "cafe", "market", "counter"],
        "bedroom": ["bedroom", "bed"],
        "park": ["park", "garden", "forest", "woods", "lake"],
        "room": ["classroom", "hallway", "corridor", "room"],
    },
}

PROP_WORDS = {
    "vi": {
        "umbrella": ["chiếc ô", "cái ô", "cây dù", "chiếc dù", "ô", "dù"],
        "bag": ["túi xách", "cái túi", "ba lô", "balo", "cặp sách", "chiếc cặp", "túi"],
        "phone": ["điện thoại"],
        "letter": ["lá thư", "bức thư", "tờ giấy", "mẩu giấy", "thư"],
        "book": ["cuốn sách", "quyển sách", "cuốn vở", "sách"],
        "newspaper": ["tờ báo", "báo"],
        "cup": ["cái cốc", "chiếc cốc", "cái ly", "chiếc ly", "tách trà", "cốc", "ly", "tách"],
        "bread": ["ổ bánh mì", "bánh mì", "ổ bánh", "chiếc bánh", "bánh"],
        "coin": ["đồng xu", "đồng tiền xu"],
        "key": ["chìa khóa", "chìa khoá"],
        "box": ["cái hộp", "chiếc hộp", "hộp quà", "hộp"],
        "bottle": ["chai nước", "cái chai", "chai"],
        "tray": ["cái khay", "khay"],
        "flower": ["bó hoa", "bông hoa", "hoa"],
        "bus": ["xe buýt", "xe bus"],
        "car": ["xe ô tô", "ô tô", "xe hơi", "taxi"],
    },
    "en": {
        "umbrella": ["umbrella"],
        "bag": ["handbag", "backpack", "bag", "suitcase"],
        "phone": ["phone", "mobile"],
        "letter": ["letter", "note", "envelope", "card"],
        "book": ["notebook", "book", "diary"],
        "newspaper": ["newspaper", "paper"],
        "cup": ["cup", "mug", "glass"],
        "bread": ["loaf", "bread", "cake", "bun"],
        "coin": ["coin"],
        "key": ["keys", "key"],
        "box": ["box", "parcel", "package"],
        "bottle": ["bottle"],
        "tray": ["tray"],
        "flower": ["flowers", "flower", "bouquet"],
        "bus": ["bus"],
        "car": ["car", "taxi", "cab"],
    },
}

FEATURE_WORDS = {
    "vi": {
        "door": ["cửa chính", "cánh cửa", "cửa ra vào", "ra cửa", "cửa"],
        "window": ["cửa sổ"],
        "seat": ["ghế sofa", "ghế", "băng ghế", "sofa"],
        "table": ["cái bàn", "bàn làm việc", "bàn"],
        "shelf": ["giá sách", "kệ sách", "cái kệ", "kệ"],
        "corner": ["góc phòng", "góc"],
        "oven": ["lò nướng", "lò"],
        "computer": ["máy tính"],
        "bed": ["giường"],
        "counter": ["quầy"],
        "light": ["đèn"],
    },
    "en": {
        "door": ["front door", "the door", "door"],
        "window": ["window"],
        "seat": ["stool", "chair", "sofa", "couch", "bench"],
        "table": ["table", "desk"],
        "shelf": ["shelf", "shelves", "bookcase"],
        "corner": ["corner"],
        "oven": ["oven", "stove"],
        "computer": ["computer", "laptop"],
        "bed": ["bed"],
        "counter": ["counter"],
        "light": ["lights", "light", "lamp"],
    },
}

ACTION_WORDS = {
    "vi": {
        "board": ["bước lên xe", "lên xe"],
        "vehicle_arrive": ["xe buýt tới", "xe buýt đến", "xe tới", "xe đến"],
        "lights_on": ["bật đèn"],
        "lights_off": ["tắt đèn"],
        "approach": ["đi lại gần", "lại gần", "tiến lại gần", "tiến đến", "đến gần"],
        "exit": ["ra khỏi", "rời khỏi", "đi mất", "bỏ đi", "rời đi"],
        "enter": ["bước vào", "đi vào", "vào nhà", "vào phòng"],
        "run": ["chạy ra", "chạy", "lao"],
        "walk": ["đi ra", "bước ra", "đi về", "đi tới", "đi", "bước", "về đến"],
        "stand_up": ["đứng dậy", "đứng lên"],
        "sit": ["ngồi xuống", "ngồi"],
        "look": ["nhìn ra", "nhìn", "ngó", "liếc", "ngắm", "quan sát", "trông thấy", "nhận ra"],
        "pick_up": ["cầm lên", "nhặt lên", "nhặt", "lấy", "cầm"],
        "hold": ["ôm", "giữ", "nghiêng ô", "che"],
        "put_down": ["đặt xuống", "đặt", "để lên", "để vào", "cho vào"],
        "give": ["đưa cho", "trao", "tặng", "đưa"],
        "open": ["mở cửa", "mở khóa", "mở"],
        "close": ["đóng cửa", "đóng"],
        "knock": ["gõ cửa", "gõ"],
        "talk": ["gọi lớn", "nói", "hỏi", "bảo", "đáp", "trả lời", "kêu", "hét", "thì thầm", "gọi"],
        "wave": ["vẫy tay", "vẫy"],
        "point": ["chỉ tay", "chỉ vào"],
        "nod": ["gật đầu"],
        "shake_head": ["lắc đầu"],
        "smile": ["mỉm cười", "cười"],
        "sad": ["thở dài", "khóc", "buồn"],
        "surprise": ["sững người", "giật mình", "ngạc nhiên", "sững sờ"],
        "fear": ["sợ hãi", "hoảng", "run rẩy", "sợ"],
        "think": ["tự hỏi", "suy nghĩ", "nghĩ", "nhớ", "định"],
        "read": ["đọc"],
        "operate": ["tắt máy", "bấm", "gõ phím", "tắt", "bật"],
        "dress": ["mặc áo", "đội mũ", "buộc", "thắt"],
        "sleep": ["ngủ thiếp", "ngủ"],
        "disappear": ["biến mất", "không còn"],
        "reveal": ["chỉ còn", "có một", "còn một", "xuất hiện"],
        "idle": ["đứng", "chờ", "đợi"],
    },
    "en": {
        "board": ["got on", "climbed aboard", "boarded", "got into the car"],
        "vehicle_arrive": ["bus came", "bus arrived", "pulled up"],
        "lights_on": ["switched on the lights", "switched on the light", "turned on the lights",
                      "turned on the light", "switched on", "turned on"],
        "lights_off": ["switched off the lights", "turned off the lights", "switched off", "turned off"],
        "approach": ["walked up to", "came closer", "approached", "went over to"],
        "exit": ["ran out", "went out", "walked out", "left the", "and left", "then left", "turned the corner"],
        "enter": ["came in", "walked in", "stepped in", "entered", "went back to", "came back"],
        "run": ["ran", "rushed", "hurried", "run"],
        "walk": ["walked", "went", "stepped", "walk", "headed"],
        "stand_up": ["stood up", "got up", "rose"],
        "sit": ["sat down", "sat", "sit"],
        "look": ["looked", "watched", "stared", "glanced", "saw", "noticed", "look"],
        "pick_up": ["picked up", "took", "grabbed", "lifted"],
        "hold": ["held", "holding", "hugged", "clutched"],
        "put_down": ["put down", "set down", "placed", "slid", "put"],
        "give": ["gave", "handed", "offered"],
        "open": ["unlocked", "opened", "open"],
        "close": ["closed", "shut"],
        "knock": ["knocked"],
        "talk": ["asked", "said", "called", "shouted", "replied", "whispered", "told", "answered"],
        "wave": ["waved"],
        "point": ["pointed"],
        "nod": ["nodded"],
        "shake_head": ["shook his head", "shook her head", "shook their head"],
        "smile": ["smiled", "laughed", "grinned"],
        "sad": ["sighed", "cried", "wept"],
        "surprise": ["froze", "gasped", "startled", "surprised"],
        "fear": ["trembled", "afraid", "scared", "shivered"],
        "think": ["wondered", "thought", "remembered", "realized"],
        "read": ["read", "reading"],
        "operate": ["typed", "pressed"],
        "dress": ["tied", "put on", "buttoned"],
        "sleep": ["fell asleep", "slept"],
        "disappear": ["disappeared", "vanished", "was gone", "were gone"],
        "reveal": ["there was", "there were", "lay a"],
        "idle": ["waiting", "waited", "stood"],
    },
}

# Person noun phrases that introduce an unnamed character: (gender, age).
PERSON_NOUNS = {
    "vi": {
        "ông cụ": ("male", "elder"), "bà cụ": ("female", "elder"), "cụ ông": ("male", "elder"),
        "cụ bà": ("female", "elder"), "người đàn ông": ("male", "adult"), "người phụ nữ": ("female", "adult"),
        "cô gái": ("female", "adult"), "chàng trai": ("male", "adult"), "cậu bé": ("male", "child"),
        "cô bé": ("female", "child"), "đứa bé": ("unknown", "child"), "bác bảo vệ": ("male", "elder"),
        "anh tài xế": ("male", "adult"), "người lạ": ("unknown", "adult"), "bà lão": ("female", "elder"),
        "ông lão": ("male", "elder"),
    },
    "en": {
        "old man": ("male", "elder"), "old woman": ("female", "elder"), "old lady": ("female", "elder"),
        "little girl": ("female", "child"), "small girl": ("female", "child"), "girl": ("female", "child"),
        "little boy": ("male", "child"), "small boy": ("male", "child"), "boy": ("male", "child"),
        "woman": ("female", "adult"), "man": ("male", "adult"), "stranger": ("unknown", "adult"),
        "child": ("unknown", "child"), "driver": ("male", "adult"),
    },
}

# Subject pronouns -> gender (or "narrator" for first person).
PRONOUNS = {
    "vi": {"tôi": "narrator", "mình": "narrator", "cô": "female", "chị": "female", "bà": "female", "nàng": "female",
           "anh": "male", "ông": "male", "cậu": "male", "hắn": "male", "gã": "male", "chú": "male",
           "bác": "unknown", "nó": "unknown", "em": "unknown"},
    "en": {"i": "narrator", "he": "male", "she": "female", "they": "unknown", "him": "male", "her": "female"},
}

# Words that never name a character even when capitalised.
NAME_STOPWORDS = {
    "vi": {"thứ", "hai", "ba", "tư", "năm", "sáu", "bảy", "chủ", "nhật", "chiều", "sáng", "trưa", "tối", "đêm",
           "khuya", "hôm", "ngày", "đến", "ở", "trên", "dưới", "trong", "ngoài", "về", "khi", "lúc", "rồi", "nhưng",
           "và", "thì", "mà", "nếu", "có", "không", "chỉ", "cảm", "ơn", "cái", "chiếc", "một", "những", "các",
           "mọi", "người", "ai", "đó", "này", "kia", "sau", "trước", "mưa", "trời", "xe", "cháu", "con", "vợ",
           "chồng", "mẹ", "bố", "ba", "má", "anh", "chị", "em", "ông", "bà", "cô", "chú", "bác", "tôi", "nó"},
    "en": {"the", "a", "an", "at", "in", "on", "he", "she", "it", "they", "i", "we", "you", "my", "his", "her",
           "their", "our", "while", "when", "then", "there", "someone", "something", "nobody", "everyone", "are",
           "is", "was", "were", "but", "and", "or", "if", "after", "before", "monday", "tuesday", "wednesday",
           "thursday", "friday", "saturday", "sunday", "january", "february", "march", "april", "may", "june",
           "july", "august", "september", "october", "november", "december", "yes", "no", "thank", "thanks",
           "please", "good", "hello", "one", "two", "it's", "that", "this", "what", "who", "where", "why", "how",
           "mr", "mrs", "ms", "dr", "god", "dear", "mom", "dad", "grandma", "grandpa"},
}

NIGHT_WORDS = {"vi": ["ban đêm", "nửa đêm", "đêm", "khuya", "tối", "chiều tối"],
               "en": ["night", "midnight", "evening", "dark", "four in the morning", "dawn"]}
DAY_WORDS = {"vi": ["buổi sáng", "sáng hôm sau", "sáng", "trưa", "ban ngày", "chiều"],
             "en": ["next morning", "morning", "noon", "afternoon", "daylight", "sunny"]}
RAIN_WORDS = {"vi": ["đổ mưa", "mưa", "ướt sũng"], "en": ["rain", "raining", "drizzle", "storm"]}
RAIN_STOP_WORDS = {"vi": ["tạnh mưa", "hết mưa", "tạnh"], "en": ["stopped raining", "rain stopped"]}
# Phrases that mark a time jump: the planner fades across the cut.
TIME_JUMP_WORDS = {"vi": ["sáng hôm sau", "hôm sau", "về đến nhà", "tối hôm đó", "đêm hôm đó", "vài ngày sau"],
                   "en": ["next morning", "the next day", "later that", "when he went back", "when she went back",
                          "hours later", "days later"]}
# Clause separators used to assign subjects to verbs within a sentence.
CLAUSE_SPLIT = {"vi": [", ", " và ", " rồi ", " thì ", " nhưng ", "; ", " cho đến khi ", " khi "],
                "en": [", ", " and ", " then ", " while ", " but ", "; ", " until ", " when "]}
# Clause-initial indefinite subjects ("someone knocked"): the actor is off screen.
INDEFINITE_SUBJECTS = {"vi": ["có người", "ai đó", "có ai"], "en": ["someone", "somebody", "something"]}
QUOTE_CHARS = '"“”«»'
# Clause-initial subjects that negate the clause ("nobody answered"): its verbs are not acted.
NEGATED_SUBJECTS = {"vi": ["không ai", "chẳng ai", "chưa ai"], "en": ["nobody", "no one", "none"]}
# Colour words -> hex fill; applied to a character's clothing or a prop mentioned just before.
COLORS = {
    "vi": {"đỏ": "#b8473f", "vàng": "#e0b43c", "xanh lá": "#5d8a52", "xanh": "#4f7fa6", "đen": "#2b2f33",
           "trắng": "#eceae0", "nâu": "#7a5a43", "tím": "#7a5a9a", "hồng": "#d98ca0", "xám": "#8a9196",
           "cam": "#d9803c"},
    "en": {"red": "#b8473f", "yellow": "#e0b43c", "green": "#5d8a52", "blue": "#4f7fa6", "black": "#2b2f33",
           "white": "#eceae0", "brown": "#7a5a43", "purple": "#7a5a9a", "pink": "#d98ca0", "grey": "#8a9196",
           "gray": "#8a9196", "orange": "#d9803c"},
}

# Letters with Vietnamese diacritics (language detection).
VI_MARKS = "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
# A capitalised word after these is a weekday or a place, not a person.
NAME_BLOCKERS = {"vi": ["thứ", "chủ", "ở", "tại"], "en": ["in", "at", "from", "to"]}
NARRATOR_NAME = {"vi": "tôi", "en": "I"}
BUS_STOP_PHRASES = ["trạm xe buýt", "bến xe buýt", "bus stop"]
CLOTHING_WORDS = ["áo", "váy", "mũ", "coat", "dress", "shirt", "jacket", "hat"]
LEADING_CONJUNCTIONS = ["và", "rồi", "thì", "nhưng", "cho đến khi", "khi", "and", "then", "while", "but", "when",
                        "until"]
ARTICLES = ["một", "chiếc", "cái", "những", "the", "a", "an"]
IT_PRONOUNS = ["nó", "it"]
BAKERY_NAMES = ["bakery", "tiệm bánh"]
# An exit phrase starting with one of these is done at running speed.
RUN_WORDS = ["ran", "run", "rushed", "hurried", "chạy", "lao"]
