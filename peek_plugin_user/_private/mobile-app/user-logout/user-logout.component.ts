import {Router} from "@angular/router";
import {
    UserService,
    UserLogoutAction,
    UserLogoutResponseTuple
} from "@peek/peek_plugin_user";
import {Component} from "@angular/core";
import {ComponentLifecycleEventEmitter, TupleActionPushService} from "@synerty/vortexjs";
import {Ng2BalloonMsgService} from "@synerty/ng2-balloon-msg";
import {TitleService} from "@synerty/peek-util";
import {switchStyleUrls} from "@synerty/peek-util/index.web";


@Component({
    selector: './peek-plugin-user-logout',
    templateUrl: './user-logout.component.web.html',
    styleUrls: [switchStyleUrls('../scss/plugin-user.web.scss')],
    moduleId: module.id
})
export class UserLogoutComponent extends ComponentLifecycleEventEmitter {

    isAuthenticating: boolean = false;

    errors: string[] = [];

    warnings: string[] = [];
    warningKeys: string[] = [];

    constructor(private balloonMsg: Ng2BalloonMsgService,
                private tupleActionService: TupleActionPushService,
                private userService: UserService,
                private router: Router,
                titleService: TitleService) {
        super();
        titleService.setTitle("User Logout");


    }

    doLogout() {
        let tupleAction = new UserLogoutAction();
        tupleAction.userName = this.userService.userDetails.userId;

        // Add any warnings
        tupleAction.acceptedWarningKeys = this.warningKeys;

        this.isAuthenticating = true;
        this.userService.logout(tupleAction, this.tupleActionService)
            .then((response: UserLogoutResponseTuple) => {

                if (response.succeeded) {
                    this.balloonMsg.showSuccess("Logout Successful");
                    this.router.navigate(['']);
                    return;
                }

                this.balloonMsg.showWarning("Logout Failed, check the warnings and try again");

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
                if (err.startsWith("Timed out")) {
                    alert("Logout Failed. The server didn't respond.");
                    this.isAuthenticating = false;
                    return;
                }
                alert(err);
                this.isAuthenticating = false;
            });

    }

    // ------------------------------
    // Display methods

    loggedInUserText() {
        return this.userService.userDetails.displayName
            + ` (${this.userService.userDetails.userId})`;
    }


}