"""PowerNext inverse search over a declared, versioned hardware catalog."""
__version__ = "0.1.1+redteam"


def recommend(request, **options):
    from .service import recommend as implementation
    return implementation(request, **options)
