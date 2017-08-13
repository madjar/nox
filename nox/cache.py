from dogpile.cache import make_region
import getpass

region = make_region().configure(
    'dogpile.cache.dbm',
    expiration_time=36000,
    arguments={'filename': '/tmp/nox.dbm.'+getpass.getuser()}
)
