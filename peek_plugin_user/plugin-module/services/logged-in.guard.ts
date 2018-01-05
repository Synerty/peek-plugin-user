import {Injectable} from "@angular/core";
import {CanActivate, Router} from "@angular/router";
import {UserService} from "./user.service";

@Injectable()
export class LoggedInGuard implements CanActivate {
    constructor(private user: UserService, private router:Router) {
    }

    canActivate() {
        if (!this.user.hasLoaded()) {
            return new Promise<boolean>((resolve, reject) => {
                this.user.loadingFinishedObservable()
                    .first()
                    .subscribe(() => {
                        resolve(this.canActivate());
                    });
            });
        }

        if (this.user.isLoggedIn())
            return true;

        this.router.navigate(['peek_plugin_user', 'login']);
        return false;
    }
}