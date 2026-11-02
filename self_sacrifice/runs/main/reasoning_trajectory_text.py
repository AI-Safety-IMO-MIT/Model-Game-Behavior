"""Shared helpers that split a reply into its reasoning sentences, without loading the model."""
import re


def reasoning_of(reply):
    """the reply up to its last command"""
    m = list(re.finditer(r"`?\$\s*(give|pass)\b", reply, re.I))
    return reply[:m[-1].start()].rstrip() if m else None


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
