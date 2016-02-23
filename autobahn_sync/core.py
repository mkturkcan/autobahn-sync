import crochet
from autobahn.twisted.wamp import Application, ApplicationRunner
from twisted.internet import defer

from .logger import logger
from .exceptions import AlreadyRunningError
from .session import SyncSession, AsyncSession
from .callbacks_runner import CallbacksRunner, ThreadedCallbacksRunner


__all__ = ('DEFAULT_AUTOBAHN_ROUTER', 'DEFAULT_AUTOBAHN_REALM', 'AutobahnSync')


DEFAULT_AUTOBAHN_ROUTER = u"ws://127.0.0.1:8080/ws"
DEFAULT_AUTOBAHN_REALM = u"realm1"
crochet_initialized = False


def _init_crochet(in_twisted=False):
    global crochet_initialized
    if crochet_initialized:
        return
    if in_twisted:
        crochet.no_setup()
    else:
        crochet.setup()
    crochet_initialized = True


# class ErrorCollector(object):
#     def check(self):
#         raise NotImplementedError()


# class InTwistedErrorCollector(ErrorCollector):
#     def __call__(self, failure):
#         raise failure.value

#     def check(self):
#         pass


class AutobahnSync(object):

    def __init__(self, prefix=None):
        self.session = None
        self._async_app = Application(prefix=prefix)
        self._async_runner = None
        self._async_session = None
        self._started = False
        self._error_collector_cls = None
        self._callbacks_runner = None

    def run(self, url=DEFAULT_AUTOBAHN_ROUTER, realm=DEFAULT_AUTOBAHN_REALM,
            in_twisted=False, blocking=False, **kwargs):
        """Start the background twisted thread and create the wamp connection

        .. note:: This function must be called first
        """
        if self._started:
            raise AlreadyRunningError("This AutobahnSync instance is already started")
        _init_crochet(in_twisted=in_twisted)

        if blocking:
            self._callbacks_runner = CallbacksRunner()
        else:
            self._callbacks_runner = ThreadedCallbacksRunner()
        if in_twisted:
            raise NotImplementedError()
            # self._in_twisted_start(url=url, realm=realm, **kwargs)
        else:
            self._out_twisted_start(url=url, realm=realm, **kwargs)
        self._started = True
        self._callbacks_runner.start()

    def stop(self):
        self._callbacks_runner.stop()

    # def _in_twisted_start(self, **kwargs):
    #     self._error_collector_cls = InTwistedErrorCollector
    #     self._async_runner = ApplicationRunner(**kwargs)
    #     d = self._async_runner.run(self._async_app, start_reactor=False)
    #     d.addErrback(self._error_collector_cls())

    def _out_twisted_start(self, **kwargs):

        @crochet.wait_for(timeout=30)
        def bootstrap():
            ready_deferred = defer.Deferred()
            logger.debug('start bootstrap')

            def register_session(config):
                logger.debug('start register_session')
                self._async_session = AsyncSession(config=config)
                self.session = SyncSession(self._async_session, self._callbacks_runner)

                def resolve(result):
                    logger.debug('callback resolve', result)
                    ready_deferred.callback(result)
                    return result

                self._async_session.on_join_defer.addCallback(resolve)

                def resolve_error(failure):
                    logger.debug('errback resolve_error', failure)
                    ready_deferred.errback(failure)

                self._async_session.on_join_defer.addErrback(resolve_error)
                return self._async_session

            self._async_runner = ApplicationRunner(**kwargs)
            d = self._async_runner.run(register_session, start_reactor=False)

            def connect_error(failure):
                ready_deferred.errback(failure)

            d.addErrback(connect_error)
            logger.debug('end bootstrap')
            return ready_deferred

        logger.debug('call bootstrap')
        bootstrap()

    def register(self, procedure=None, options=None):
        "Decorator for the register"
        assert self.session

        def decorator(func):
            self.session.register(endpoint=func, procedure=procedure, options=options)

        return decorator

    def subscribe(self, topic, options=None):
        "Decorator for the subscribe"
        assert self.session

        def decorator(func):
            self.session.subscribe(handler=func, topic=topic, options=options)

        return decorator
