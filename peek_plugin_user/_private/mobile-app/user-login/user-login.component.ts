import {Router} from "@angular/router";
import {
    UserListItemTuple,
    UserLoginAction,
    UserLoginResponseTuple,
    UserService
} from "@peek/peek_plugin_user";
import {UserTupleService} from "@peek/peek_plugin_user/_private/user-tuple.service";
import {Component} from "@angular/core";
import {
    ComponentLifecycleEventEmitter,
    TupleActionPushService,
    TupleDataObserverService,
    TupleDataOfflineObserverService,
    TupleSelector
} from "@synerty/vortexjs";
import {Ng2BalloonMsgService} from "@synerty/ng2-balloon-msg";
import {TitleService} from "@synerty/peek-util";

@Component({
    selector: './peek-plugin-user-login',
    templateUrl: './user-login.component.web.html',
    styleUrls: ['../scss/plugin-user.web.scss'],
    moduleId: module.id
})
export class UserLoginComponent extends ComponentLifecycleEventEmitter {

    users: Array<UserListItemTuple> = [];
    selectedUser: UserLoginAction = new UserLoginAction();
    isAuthenticating: boolean = false;
    test: any = "";

    errors: string[] = [];

    warnings: string[] = [];
    warningKeys: string[] = [];

    constructor(private balloonMsg: Ng2BalloonMsgService,
                private tupleService: UserTupleService,
                private userService: UserService,
                private router: Router,
                titleService: TitleService) {
        super();
        titleService.setTitle("User Login");

        let selectAUser = new UserListItemTuple();
        selectAUser.displayName = "Select a User";

        let tupleSelector = new TupleSelector(UserListItemTuple.tupleName, {});
        this.tupleService.observer.subscribeToTupleSelector(tupleSelector)
            .takeUntil(this.onDestroyEvent)
            .subscribe((tuples: UserListItemTuple[]) => {
                let blank = new UserListItemTuple();
                blank.displayName = '--- select ---';
                this.users = [blank];
                this.users.add(tuples);
                console.log("UserListItemTuple Tuples len = " + tuples.length.toString());
            });
    }

    isSelectedUserNull(): boolean {
        return this.selectedUser.userName == null || this.selectedUser.userName === '';
    }

    webDisplayText(item: UserListItemTuple): string {
        if (item.userId == null || item.userId === '')
            return item.displayName; // For the --select-- case

        return `${item.displayName} (${item.userId})`;

    }

    loginText() {
        if (this.isSelectedUserNull())
            return "Login";

        return `I'm ${this.selectedUser.userName}, LOG ME IN`;
    }

    isLoginEnabled(): boolean {
        return !this.isSelectedUserNull()
            && !this.isAuthenticating
            && this.selectedUser.password && this.selectedUser.password.length != 0
            && this.selectedUser.vehicleId && this.selectedUser.vehicleId.length != 0;
    }

    doLogin() {

        let tupleAction = this.selectedUser;

        // Add any warnings
        tupleAction.acceptedWarningKeys = this.warningKeys;

        let userDetails: UserListItemTuple = this.users
            .filter(item => item.userId === this.selectedUser.userName)[0];

        this.isAuthenticating = true;
        this.userService.login(tupleAction, userDetails)
            .then((response: UserLoginResponseTuple) => {

                if (response.succeeded) {
                    this.balloonMsg.showSuccess("Login Successful");
                    this.router.navigate(['']);
                    return;
                }

                this.balloonMsg.showWarning("Login Failed, check the warnings and try again");

                this.errors = response.errors;
                this.warnings = [];
                for (let key in response.warnings) {
                    if (!response.warnings.hasOwnProperty(key))
                        continue;
                    for (let item of response.warnings[key].split('\n')) {
                        this.warnings.push(item);
                    }
                    this.warningKeys.push(key);
                }
                this.isAuthenticating = false;

            })
            .catch((err) => {
                if (err.toString().startsWith("Timed out")) {
                    alert("Login Failed. The server didn't respond.");
                    this.isAuthenticating = false;
                    return;
                } else if (err.toString().length == 0) {
                    alert("An error occurred when logging in.");
                }
                alert(err);
                this.isAuthenticating = false;
            });

    }


}