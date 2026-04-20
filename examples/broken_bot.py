"""Top-level shim so ``python examples/broken_bot.py`` still works.

The canonical location is ``ghostgate.examples.broken_bot`` so it can be
invoked as a module after ``pip install``:

    python -m ghostgate.examples.broken_bot
"""

from ghostgate.examples.broken_bot import main

if __name__ == "__main__":
    main()
