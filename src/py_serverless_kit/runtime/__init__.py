"""Portable function runtime.

Everything in this package MUST stay standard-library only and compatible with
Python 3.9+, because it is vendored into every deployment artifact and executed
on runtimes we do not control (Tencent / Huawei still default to 3.9).
"""
