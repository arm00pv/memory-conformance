#!/usr/bin/env python3
"""words.py - what a question is actually asking about.

TWO TOOLS IN THIS REPOSITORY NEED THE SAME ANSWER TO "WHAT WORDS IN THIS PHRASE CARRY THE MEANING",
and having two answers is how a repository ends up contradicting itself. validate_corpus.py compares a
question against records to prove that an unanswerable question is unanswerable and an adversarial one
has a competitor; retrieval.py uses the same reduction to re-ask every question as a keyword string.
One list, one tokenizer, imported by both.

WHY A STOPWORD LIST RATHER THAN A STEMMER: the questions are short and the vocabulary is small, so the
cheap thing works and the expensive thing would hide its own failures. The list is deliberately short,
and every word it removes is a word that cannot distinguish one record from another anyway.
"""
import re

STOP = set("""a an the is are was were be been being am do does did done doing of in on at to for from
by with within without about into onto over under between among through during before after above below
up down out off again further then once here there when where why how all any both each few more most
other some such no nor not only own same so than too very can could should would may might must will
shall have has had having i me my we our us you your he him his she her it its they them their this
that these those what which who whom whose get gets got make makes made take takes taken give gives
give use used using need needs want wants keep keeps held hold put puts set sets run runs say says said
tell tells told find finds found know knows ask asks one two three many much long often usually
doesn dont doesn isn aren wasn weren whats hows that's it's
and or but if because while whilst whereas whether though although unless until since as per via upon
both either neither also just still yet even ever never always already
everyone someone anyone nobody whose""".split())


def tokens(text):
    """The words of a phrase that could distinguish one record from another.

    A trailing s is dropped so that "keys" meets "key", which is the only morphology this corpus needs.
    Digits are kept: "5432" is the most distinctive word in the sentence that contains it.
    """
    out = []
    for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if w in STOP:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def keyword_form(query):
    """The same question with the words that carry no meaning taken out.

    A person types a question; a search box wants the words. The distance between the two is a property
    of the subject - one that indexes words gets the keyword form and misses the question form, one that
    answers questions may be the other way round - and it is invisible in a score computed from questions
    alone. This is the mechanical, identical-for-everyone way to ask both: no authoring, so no author's
    vocabulary in it.
    """
    kept = tokens(query)
    return " ".join(kept) if kept else (query or "").strip()
