from data import Version


def sort_by_occurrence(d):
    result_xx = sorted(d.items(), key=lambda x: x[1])
    return [ix[0] for ix in result_xx], result_xx


def get_and_merge_from_file(d, address_mapping, file_path):
    with open(file_path, "r") as f:
        address_size = 0
        while True:
            line = f.readline()
            if not line:
                break
            line = line.strip()
            if "," in line:
                zip_code, version_pk = line.split(",")
            else:
                zip_code, version_pk = line.split("|")
            if version_pk not in d:
                d[version_pk] = 0
            d[version_pk] += 1

            if zip_code not in address_mapping:
                address_mapping[zip_code] = []
            address_size += 1
            address_mapping[zip_code].append(version_pk)
    return address_size


def load_from_file(files):
    d = {}
    address_mapping = {}
    address_size = 0
    for file_name in files:
        new_address_size = get_and_merge_from_file(d, address_mapping, file_name)
        address_size += new_address_size
    new_d = {}
    for version, count in d.items():
        new_d[version] = count

    zip_codes_counter_dict = {}
    for zip_code, versions in address_mapping.items():
        zip_codes_counter_dict[zip_code] = len(versions)

    return address_size, new_d, address_mapping


def get_version_id_mapping(d, address_mapping):
    new_d = {}
    version_id_mapping = {}
    reversed_version_id_mapping = {}

    for i, (version, count) in enumerate(d.items()):
        new_d[i] = count
        version_id_mapping[i] = version
        reversed_version_id_mapping[version] = i

    new_address_mapping = {}
    for zip_code, versions in address_mapping.items():
        new_versions = []
        for version in versions:
            new_versions.append(reversed_version_id_mapping[version])
        new_address_mapping[zip_code] = new_versions

    return version_id_mapping, new_d, new_address_mapping


def get_versions(file_names):
    address_size_x, d_x, address_mapping = load_from_file(file_names)
    version_id_to_name_mapping, d_x, address_mapping = get_version_id_mapping(
        d_x, address_mapping
    )
    versions = []
    for key, value in d_x.items():
        versions.append(Version(version_id=key, quantity=value))
    return versions, address_mapping
