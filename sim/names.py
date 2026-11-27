"""The sound system of the nation's language, and the names built from it.

For now this only makes names. The language stage builds vocabulary and
sound change on top of the same sound system, so names and words will
always sound like they come from the same tongue.
"""

CONSONANT_POOL = ["p", "t", "k", "b", "d", "g", "m", "n", "s", "f", "v", "r", "l",
                  "h", "th", "sh", "w", "y", "z", "ch"]
VOWEL_POOL = ["a", "e", "i", "o", "u", "ae", "ei", "ou", "y"]
CODA_POOL = ["n", "r", "l", "s", "th", "m", "k", "st", "nd", "rn"]


def make_phonology(rng):
    """Pick a random but consistent set of sounds for this nation."""
    consonants = rng.sample(CONSONANT_POOL, rng.randint(10, 14))
    vowels = rng.sample(VOWEL_POOL, rng.randint(4, 6))
    codas = rng.sample(CODA_POOL, rng.randint(4, 7))
    for must in ["a", "e"]:
        if must not in vowels:
            vowels.append(must)
    return {
        "consonants": consonants,
        "vowels": vowels,
        "codas": codas,
        # chance a syllable ends in a consonant
        "coda_rate": round(rng.uniform(0.25, 0.55), 2),
        # weights for 1, 2 or 3 syllable words
        "length_weights": [rng.randint(2, 4), rng.randint(4, 6), rng.randint(1, 3)],
        "female_endings": rng.sample(["a", "e", "is", "ia", "el", "ine", "y"], 3),
        "male_endings": rng.sample(["o", "an", "ek", "us", "or", "im", "ar"], 3),
    }


def syllable(ph, rng, allow_coda=True):
    s = ""
    if rng.random() < 0.85:
        s += rng.choice(ph["consonants"])
    s += rng.choice(ph["vowels"])
    if allow_coda and rng.random() < ph["coda_rate"]:
        s += rng.choice(ph["codas"])
    return s


def word(ph, rng, syllables=None):
    if syllables is None:
        syllables = rng.choices([1, 2, 3], weights=ph["length_weights"])[0]
    parts = [syllable(ph, rng, allow_coda=(i == syllables - 1) or rng.random() < 0.3)
             for i in range(syllables)]
    w = "".join(parts)
    # tidy doubled vowels like "aea"
    for v in ph["vowels"]:
        w = w.replace(v + v, v)
    return w


def given_name(ph, rng, sex):
    root = word(ph, rng, syllables=rng.choice([1, 2, 2]))
    if rng.random() < 0.6:
        ends = ph["female_endings"] if sex == "f" else ph["male_endings"]
        end = rng.choice(ends)
        if root[-1] in "aeiouy" and end[0] in "aeiouy":
            root = root[:-1]
        root += end
    return root.capitalize()


def place_name(ph, rng):
    return word(ph, rng, syllables=rng.choice([2, 2, 3])).capitalize()


def build_name_pools(ph, rng):
    """Shared pools so names repeat across families, like real naming customs."""
    def unique(make, n):
        seen = set()
        out = []
        tries = 0
        while len(out) < n and tries < n * 50:
            tries += 1
            nm = make()
            if 3 <= len(nm) <= 10 and nm not in seen:
                seen.add(nm)
                out.append(nm)
        return out
    return {
        "f": unique(lambda: given_name(ph, rng, "f"), 120),
        "m": unique(lambda: given_name(ph, rng, "m"), 120),
        "family": unique(lambda: word(ph, rng, syllables=rng.choice([2, 2, 3])).capitalize(), 140),
    }
