# net requires this file, that only contains some helper methods
# but net file would be too large for micropython otherwise
import ujson as json


_CONFIG_FILE = "netconf.json"  # this file must contain, hosname, password, known networks, port (...)


def read_cfg(key=None):  # key can be specified for a single entry, otherwise returns all data
    try:
        with open(_CONFIG_FILE, 'r') as f:
            dat = json.loads(f.read())
            if key is not None:
                return dat[key]
            return dat
    except KeyError:
        return None


def write_cfg(dat):  # dat = data dict (format must be exactly of type see json file)
    with open(_CONFIG_FILE, 'w') as f:
        f.write(json.dumps(dat))


def _deepcopy(v):  # recursive, but only for lists/tuples/dicts (and atomic values of course, but not objects)
    if isinstance(v, (int, float, bool, bytes, str, type, range, type(None), type(Ellipsis))):
        return v  # atomic value
    elif isinstance(v, (tuple, list)):
        return type(v)(_deepcopy(x) for x in v)
    elif isinstance(v, bytearray):
        return bytearray(v)  # only consists of ints/bytes
    elif isinstance(v, dict):
        return {_deepcopy(k): _deepcopy(v[k]) for k in v}
    else:
        raise NotImplementedError  # obj not supported, use official copy.deepcopy in micropython-lib


def json_prep_dict(v):
    # Modifies the given dict <v> (any value) by changing all dict-keys recursivly to strings.
    # This is required for 8.7.2018 as the ujson module does not work properly, because it
    # converts dicts like {1: 2} to '{1: 2}' instead of '{"1": 2}' (keys need to be strings!).
    # Returns the modified dict (v remains unchanged).

    if isinstance(v, (tuple, list)):
        return (json_prep_dict(x) for x in v)  # list and tuples same in JSON
    elif isinstance(v, dict):
        return {str(k): json_prep_dict(v) for k, v in v.items()}
    else:  # note: objects with dicts as attr or anything will not be recognized!
        return v


def find_changed_vals(dat_old, dat_new):
    data_changed = {}  # changed attributes

    for attr in dat_new:  # check every key, if it has changed or is new (only non-private)
        if attr in dat_old:
            if dat_old[attr] != dat_new[attr]:
                if isinstance(dat_new[attr], dict) and isinstance(dat_old[attr], dict):  # only send
                    data_changed[attr] = find_changed_vals(dat_old[attr], dat_new[attr])  # changed keys
                else:
                    data_changed[attr] = dat_old[attr] = _deepcopy(dat_new[attr])  # local and com change
        elif len(attr) != 0 and attr[0] != '_':  # new key
            data_changed[attr] = dat_old[attr] = _deepcopy(dat_new[attr])  # local and comm change

    return data_changed


def get_var(varls, cache):  # execute GET command: find local variable and return it (no cache lookup)
    # <varls> can be a single variable or a list of variables/keys to support objects, dicts, list and tuples,
    # e.g. ['objA', 'objB', 'keyC', 'attrD', indexE] for objA.objB[keyC].attrD[indexE]
    # the variable found is updated in cache dict (or updated in cache if was before)
    if isinstance(varls, str):
        varls = (varls,)
    elif not isinstance(varls, (list, tuple)):
        return

    val = locals()
    for var in varls:
        if isinstance(val, dict):  # dict[var_anything]
            if var not in val or isinstance(var, str) and len(var) != 0 and var[0] == '_':
                return  # key err or private member
            val = val[var]
        elif isinstance(val, (list, tuple)):  # list/tuple[var_int]
            if not isinstance(var, int):
                return
            val = val[var]
        else:  # data.var_str
            if not isinstance(var, str) or len(var) == 0 or var[0] == '_' or not hasattr(val, var):
                return  # attribute err. non-private attribute must be given a non-empty string and has to exist
            val = getattr(val, var)

    # variable needs to be returned in a dict; additionally set the variable in cached data
    retmsg = {}
    msg = retmsg
    for var in varls[:-1]:
        if var not in cache:
            cache[var] = {}
        cache = cache[var]
        msg[var] = {}
        msg = msg[var]
    cache[varls[-1]] = val
    msg[varls[-1]] = val

    return retmsg


def set_var(varls, val, cache, localObj):  # e.g. set(('io', 'rly', 'BL'), True), possible only if setter fun defined
    if isinstance(varls, str):
        varls = (varls,)
    elif isinstance(varls, list):
        varls = tuple(varls)
    if not isinstance(varls, tuple) or len(varls) <= 1:  # cannot set whole local var like 'ecu' or 'ctrl'
        return

    try:  # first check if variable exists
        for i in range(len(varls)-1):  # all apart from last to make setting possible
            cache = cache[varls[i]]
    except KeyError:
        return  # object/attribute/key not existing, not cached or not setable
    if varls[-1] not in cache:
        return

    # now do the real job (hard coded); data is reference to the main object like ecu or ctrl:
    if varls[0] == 'ctrl':
        if varls[1] == 'rly':
            # first perform local update of cached data (not req., but prevents unnecessary update()-call)
            cache[varls[-1]] = val  # update local data
            localObj[varls[0]].set_rly(varls[-1], val)
        elif varls[1] == 'mode':  # no local update here to make sure user sees whether change was successful
            if isinstance(val, int):
                localObj[varls[0]].mode = val
