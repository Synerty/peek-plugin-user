import {addTupleType, TupleActionABC} from "@synerty/vortexjs";
import {userTuplePrefix} from "../../_private/PluginNames";

@addTupleType
export class UserLogoutAction extends TupleActionABC {
    public static readonly tupleName = userTuplePrefix + "UserLogoutAction";

    constructor() {
        super(UserLogoutAction.tupleName); // Matches server side
    }

    userName: string;
    deviceToken: string;

    // A list of accepted warning keys
    // If any server side warnings occur and they are in this list then the logoff
    // continues.
    acceptedWarningKeys: string[] = [];
}
