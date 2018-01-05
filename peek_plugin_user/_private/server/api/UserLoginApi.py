import logging
from datetime import datetime

import pytz
from twisted.cred.error import LoginDenied
from twisted.internet.defer import Deferred, inlineCallbacks

from peek_core_device.server.DeviceApiABC import DeviceApiABC
from peek_plugin_user._private.server.api.UserHookApi import UserHookApi
from peek_plugin_user._private.server.api.UserInfoApi import UserInfoApi
from peek_plugin_user._private.server.controller.PasswordUpdateController import \
    PasswordUpdateController
from peek_plugin_user._private.storage.InternalUserTuple import InternalUserTuple
from peek_plugin_user._private.storage.UserLoggedIn import UserLoggedIn
from peek_plugin_user._private.tuples.UserLoggedInTuple import UserLoggedInTuple
from peek_plugin_user.server.UserDbErrors import UserIsNotLoggedInToThisDeviceError, \
    UserNotFoundException
from peek_plugin_user.server.UserLoginApiABC import UserLoginApiABC
from peek_plugin_user.tuples.login.UserLoginAction import UserLoginAction
from peek_plugin_user.tuples.login.UserLoginResponseTuple import UserLoginResponseTuple
from peek_plugin_user.tuples.login.UserLogoutAction import UserLogoutAction
from peek_plugin_user.tuples.login.UserLogoutResponseTuple import UserLogoutResponseTuple
from vortex.DeferUtil import deferToThreadWrapWithLogger
from vortex.TupleSelector import TupleSelector

logger = logging.getLogger(__name__)

USER_ALREADY_LOGGED_ON_KEY = 'pl-user.USER_ALREADY_LOGGED_ON'
DEVICE_ALREADY_LOGGED_ON_KEY = 'pl-user.DEVICE_ALREADY_LOGGED_ON_KEY'


class UserLoginApi(UserLoginApiABC):
    #: A reference to the core device plugins API
    _deviceApi: DeviceApiABC

    def __init__(self, deviceApi: DeviceApiABC,
                 dbSessionCreator,
                 hookApi: UserHookApi,
                 infoApi: UserInfoApi):
        self._deviceApi = deviceApi
        self._hookApi = hookApi
        self._infoApi = infoApi
        self._dbSessionCreator = dbSessionCreator
        self._tupleObservable = None

    def setTupleObserver(self, tupleObservable):
        self._tupleObservable = tupleObservable

    def shutdown(self):
        pass

    def _checkPassBlocking(self, ormSession, userName, password) -> bool:
        if not password:
            return False

        users = (
            ormSession
                .query(InternalUserTuple)
                .filter(InternalUserTuple.userName == userName)
                .all()
        )

        if not users:
            raise UserNotFoundException(userName)

        user = users[0]
        return user.password == PasswordUpdateController.hashPass(password)

    @deferToThreadWrapWithLogger(logger)
    def _logoutInDb(self, logoutTuple: UserLogoutAction):
        """
        Returns Deferred[UserLogoutResponseTuple]
        """

        session = self._dbSessionCreator()
        try:
            # Check if the user is actually logged into this device.
            qry = (
                session.query(UserLoggedIn)
                    .filter(UserLoggedIn.userName == logoutTuple.userName)
                    .filter(
                    UserLoggedIn.deviceToken == logoutTuple.deviceToken)
            )

            if qry.count() == 0:
                raise UserIsNotLoggedInToThisDeviceError(logoutTuple.userName)

            session.delete(qry.one())
            session.commit()

        finally:
            session.close()

    @inlineCallbacks
    def logout(self, logoutTuple: UserLogoutAction) -> Deferred:
        """ Logout

        :param logoutTuple: The tuple containing the information to process
                                for the logout.

        :return A deferred that fires with List[UserLogoutResponseTuple]
        """

        response = UserLogoutResponseTuple(
            userName=logoutTuple.userName,
            deviceToken=logoutTuple.deviceToken,
            acceptedWarningKeys=logoutTuple.acceptedWarningKeys,
            succeeded=True)

        # Give the hooks a chance to fail the logout
        yield self._hookApi.callLogoutHooks(response)

        # If there are no problems, proceed with the logout.
        if response.succeeded:
            yield self._logoutInDb(logoutTuple)

        self._tupleObservable.notifyOfTupleUpdate(
            TupleSelector(UserLoggedInTuple.tupleType(),
                          selector=dict(userName=logoutTuple.userName))
        )

        return response

    @deferToThreadWrapWithLogger(logger)
    def _loginInDb(self, loginTuple: UserLoginAction, singleDevice: bool = True):
        """
        Returns Deferred[UserLoginResponseTuple]

        """

        assert singleDevice, "Multiple device login not implemented"
        userName = loginTuple.userName
        password = loginTuple.password
        acceptedWarningKeys = set(loginTuple.acceptedWarningKeys)
        deviceToken = loginTuple.deviceToken

        responseTuple = UserLoginResponseTuple(
            userName=userName,
            userToken="Not implemented",
            succeeded=False,
            acceptedWarningKeys=loginTuple.acceptedWarningKeys
        )

        if not deviceToken:
            raise Exception("peekToken must be supplied")

        thisDeviceDescription = self._deviceApi.deviceDescriptionBlocking(deviceToken)

        ormSession = self._dbSessionCreator()
        try:
            if not self._checkPassBlocking(ormSession, userName, password):
                raise LoginDenied("Username or Password is incorrect")

            # Find any current login sessions
            userLoggedIn = (ormSession.query(UserLoggedIn)
                .filter(UserLoggedIn.userName == userName)
                .all())
            userLoggedIn = userLoggedIn[0] if userLoggedIn else None

            loggedInElsewhere = (
                ormSession.query(UserLoggedIn)
                    .filter(UserLoggedIn.deviceToken != deviceToken)
                    .filter(UserLoggedIn.userName == userName)
                    .all())

            if len(loggedInElsewhere) not in (0, 1):
                raise Exception("Found more than 1 ClientDevice for"
                                + (" token %s" % deviceToken))

            loggedInElsewhere = loggedInElsewhere[0] if loggedInElsewhere else None

            sameDevice = userLoggedIn and loggedInElsewhere is None

            # If the user is logged in, but not to this client device, raise exception
            if userLoggedIn and not sameDevice:
                if USER_ALREADY_LOGGED_ON_KEY in acceptedWarningKeys:
                    self._forceLogout(ormSession,
                                      userName,
                                      loggedInElsewhere.deviceToken)
                    userLoggedIn = False

                else:
                    otherDeviceDescription = self._deviceApi.deviceDescriptionBlocking(
                        loggedInElsewhere.deviceToken
                    )
                    responseTuple.setFailed()
                    responseTuple.addWarning(
                        USER_ALREADY_LOGGED_ON_KEY,
                        "User %s is already logged in, on device %s" % (
                            userName, otherDeviceDescription)
                    )

                    return responseTuple

            # If we're logging into the same device, but already logged in
            if sameDevice:  # Logging into the same device
                sameDeviceDescription = self._deviceApi.deviceDescriptionBlocking(
                    userLoggedIn.deviceToken
                )

                responseTuple.deviceToken = userLoggedIn.deviceToken
                responseTuple.deviceDescription = sameDeviceDescription
                return responseTuple

            anotherUserOnThatDevice = (
                ormSession.query(UserLoggedIn)
                    .filter(UserLoggedIn.deviceToken == deviceToken)
                    .filter(UserLoggedIn.userName != userName)
                    .all()
            )

            if anotherUserOnThatDevice:
                anotherUserOnThatDevice = anotherUserOnThatDevice[0]
                if DEVICE_ALREADY_LOGGED_ON_KEY in acceptedWarningKeys:
                    self._forceLogout(ormSession,
                                      anotherUserOnThatDevice.userName,
                                      anotherUserOnThatDevice.deviceToken)

                else:
                    responseTuple.setFailed()
                    responseTuple.addWarning(
                        DEVICE_ALREADY_LOGGED_ON_KEY,
                        "User %s is currently logged into this device : %s" % (
                            anotherUserOnThatDevice.userName,
                            thisDeviceDescription)
                    )

                    return responseTuple

            # Create the user logged in entry

            newUser = UserLoggedIn(userName=userName,
                                   loggedInDateTime=datetime.now(pytz.utc),
                                   deviceToken=deviceToken)
            ormSession.add(newUser)
            ormSession.commit()

            # Respond with a successful login
            responseTuple.deviceToken = deviceToken
            responseTuple.deviceDescription = thisDeviceDescription
            responseTuple.succeeded = True
            return responseTuple

        finally:
            ormSession.close()

    @inlineCallbacks
    def login(self, loginTuple: UserLoginAction):
        """
        Returns Deferred[UserLoginResponseTuple]

        """
        loginResponse = None
        try:
            loginResponse = yield self._loginInDb(loginTuple)
            yield self._hookApi.callLoginHooks(loginResponse)

        # except UserAlreadyLoggedInError as e:
        #     pass
        #
        # except DeviceAlreadyLoggedInError as e:
        #     pass
        #
        # except UserIsNotLoggedInToThisDeviceError as e:
        #     pass

        except Exception as e:

            # Log the user out again if the hooks fail
            logoutTuple = UserLogoutAction(
                userName=loginTuple.userName,
                deviceToken=loginTuple.deviceToken)

            # Force logout, we don't care if it works or not.
            try:
                yield self._logoutInDb(logoutTuple)
            except UserIsNotLoggedInToThisDeviceError:
                pass

            raise e

        self._tupleObservable.notifyOfTupleUpdate(
            TupleSelector(UserLoggedInTuple.tupleType(),
                          selector=dict(userName=loginTuple.userName))
        )

        return loginResponse

    def _forceLogout(self, ormSession, userName, deviceToken):
        (
            ormSession.query(UserLoggedIn)
                .filter(UserLoggedIn.userName == userName)
                .filter(UserLoggedIn.deviceToken == deviceToken)
                .delete(synchronize_session=False)
        )
