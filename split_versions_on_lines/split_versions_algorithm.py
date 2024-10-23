import time
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable

from data import LineConfiguration, CoMailFacility, Line, Version
from file import get_versions


@dataclass
class SplitVersionsSolution:
    line_versions_tuple_list: list[tuple[str, int]] = field(default_factory=list)


class SplitVersionsGenerator:

    def __init__(self, co_mail_facility: CoMailFacility, versions: list[Version]):
        self.co_mail_facility = co_mail_facility
        self.line_configs = self._merge_line_configurations_by_max_limit()

        self.versions_to_split_strategy_method_map = {
            self.VersionsToSplitStrategy.AVERAGE_VERSIONS: self.get_versions_to_split_average,
            self.VersionsToSplitStrategy.BIGGEST_VERSIONS: self.get_versions_to_split_the_biggest,
        }
        self.versions = self._sort_versions_by_quantity(versions)
        self.version_to_quantity_mapping = {
            version.version_id: version.quantity for version in versions
        }

        self.version_id_to_version_map = {
            version.version_id: version for version in versions
        }
        self.number_of_all_existing_pockets = sum(
            [lc.pockets * lc.size for lc in self.line_configs]
        )

        self.calculated_solutions: list["SplitVersionsSolution"] = []

    def generate(self, n: int):
        max_number_of_all_versions_to_split = self.number_of_all_existing_pockets - len(
            self.versions
        )
        max_number_of_pieces = sum([version.quantity for version in self.versions])

        self.generate_recursive_solution(
            self.line_configs,
            self.version_to_quantity_mapping,
            [v.version_id for v in self.versions],
            max_number_of_all_versions_to_split,
            max_number_of_pieces,
            SplitVersionsSolution(),
        )
        self.check_solutions()
        return self.calculated_solutions

    def generate_recursive_solution(
        self,
        line_configs_left: list["LineConfig"],
        version_to_quantity_mapping: dict[str, int],
        versions: list[str],
        max_number_of_versions_to_split: int,
        number_of_pieces_left: int,
        solution: "SplitVersionsSolution",
    ):
        current_line_config = line_configs_left[0]
        line_configs_tail = line_configs_left[1:]

        if not line_configs_tail:
            number_of_used_pieces, version_values_tuple = self.calculate_versions_used(
                version_to_quantity_mapping, versions
            )
            if self.is_line_config_valid(
                number_of_used_pieces,
                len(version_values_tuple),
                version_values_tuple,
                current_line_config,
            ):
                if len(versions) == current_line_config.pockets:
                    solution.line_versions_tuple_list.append([version_values_tuple])
                    self.calculated_solutions.append(solution)

        # If we do not need to use all pockets, lower range starting point here
        for number_of_pockets_to_use in range(
            current_line_config.pockets,
            current_line_config.pockets * current_line_config.size + 1,
        ):
            for number_of_versions_to_split in range(
                0, min(max_number_of_versions_to_split, number_of_pockets_to_use) + 1
            ):
                for versions_to_cut_strategy in [
                    self.VersionsToSplitStrategy.AVERAGE_VERSIONS,
                    self.VersionsToSplitStrategy.BIGGEST_VERSIONS,
                ]:
                    versions_to_cut_strategy_method = (
                        self.versions_to_split_strategy_method_map[
                            versions_to_cut_strategy
                        ]
                    )

                    number_of_versions_to_go_next_lines = (
                        len(versions)
                        - number_of_pockets_to_use
                        + number_of_versions_to_split
                    )
                    if number_of_versions_to_go_next_lines > sum(
                        [lc.pockets * lc.size for lc in line_configs_tail]
                    ):
                        # Too many versions will go next lines, so they will not fit in all pockets,
                        #   even without splitting.
                        continue

                    expected_number_of_pieces_to_use = number_of_pieces_left - sum(
                        [lc.max_quantity_all_lines for lc in line_configs_tail]
                    )
                    if expected_number_of_pieces_to_use < 0:
                        # It means e.g. that order is reversed
                        expected_number_of_pieces_to_use = min(
                            number_of_pieces_left,
                            current_line_config.max_quantity_all_lines,
                        )

                    (
                        new_version_to_quantity_mapping,
                        new_versions,
                        number_of_used_pieces,
                        version_values_tuple,
                    ) = self.split_versions(
                        versions_to_cut_strategy_method,
                        version_to_quantity_mapping,
                        expected_number_of_pieces_to_use,
                        number_of_pockets_to_use,
                        number_of_versions_to_split,
                    )

                    if not new_version_to_quantity_mapping:
                        continue

                    if not new_versions:
                        new_versions, _ = self._sort_versions_by_pieces_used(
                            new_version_to_quantity_mapping
                        )

                    if not self.is_line_config_valid(
                        number_of_used_pieces,
                        number_of_pockets_to_use,
                        version_values_tuple,
                        current_line_config,
                    ):
                        continue

                    new_result = deepcopy(solution)
                    new_result.line_versions_tuple_list.append([version_values_tuple])
                    self.generate_recursive_solution(
                        line_configs_tail,
                        new_version_to_quantity_mapping,
                        new_versions,
                        max_number_of_versions_to_split - number_of_versions_to_split,
                        number_of_pieces_left - number_of_used_pieces,
                        new_result,
                    )

    def split_versions(
        self,
        versions_to_split_strategy_method: Callable,
        version_to_quantity_mapping: dict[str, int],
        expected_number_of_pieces_to_use,
        number_of_pockets_to_use,
        number_of_versions_to_split,
    ):
        estimated_number_of_pieces_used_for_split = int(
            expected_number_of_pieces_to_use
            + expected_number_of_pieces_to_use
            * (number_of_versions_to_split / number_of_pockets_to_use)
        )
        versions, _ = self._sort_versions_by_pieces_used(version_to_quantity_mapping)

        if len(versions) <= number_of_versions_to_split:
            return (
                version_to_quantity_mapping,
                versions,
                *self.calculate_versions_used(version_to_quantity_mapping, versions),
            )

        version_values = [
            version_to_quantity_mapping[version_id] for version_id in versions
        ]
        used_pieces_count, version_values_tuple = versions_to_split_strategy_method(
            version_to_quantity_mapping,
            versions,
            version_values,
            number_of_pockets_to_use,
            number_of_versions_to_split,
            estimated_number_of_pieces_used_for_split,
        )

        used_versions_set = set([vt[0] for vt in version_values_tuple])
        new_version_to_quantity_mapping: dict[str, int] = {}
        new_versions = []
        for version_id in versions:
            if version_id not in used_versions_set:
                new_versions.append(version_id)
                new_version_to_quantity_mapping[version_id] = (
                    version_to_quantity_mapping[version_id]
                )

        if number_of_versions_to_split:
            number_of_pieces_to_split = (
                used_pieces_count - expected_number_of_pieces_to_use
            )
            number_of_pieces_after_split = used_pieces_count
            result_list_with_elements_to_cut = list(reversed(version_values_tuple))[
                :number_of_versions_to_split
            ]
            ratio = 1 - (
                number_of_pieces_to_split
                / sum([t[1] for t in result_list_with_elements_to_cut])
            )

            version_to_split_pieces_go_next_mapping: dict[str, int] = {}
            result = deepcopy(version_values_tuple[:-number_of_versions_to_split])
            for i, (version_id, version_count) in enumerate(
                reversed(result_list_with_elements_to_cut)
            ):
                if i == len(result_list_with_elements_to_cut) - 1:
                    number_of_split_pieces_left = version_count - (
                        number_of_pieces_after_split - expected_number_of_pieces_to_use
                    )
                else:
                    number_of_split_pieces_left = int(version_count * ratio)
                number_of_pieces_after_split = number_of_pieces_after_split - (
                    version_count - number_of_split_pieces_left
                )
                result.append((version_id, number_of_split_pieces_left))
                version_to_split_pieces_go_next_mapping[version_id] = (
                    version_count - number_of_split_pieces_left
                )

            assert number_of_pieces_after_split == expected_number_of_pieces_to_use
            version_values_tuple = result

            for version_id, quantity in version_to_split_pieces_go_next_mapping.items():
                new_version_to_quantity_mapping[version_id] = quantity
                new_versions.append(version_id)

            number_of_used_pieces = expected_number_of_pieces_to_use
        else:
            number_of_used_pieces = used_pieces_count

        return (
            new_version_to_quantity_mapping,
            new_versions,
            number_of_used_pieces,
            version_values_tuple,
        )

    def get_versions_to_split_average(
        self,
        version_to_quantity_mapping: dict[str, int],
        versions: list[str],
        version_values: list[int],
        pockets: int,
        number_of_versions_to_split: int,
        limit_max: int,
    ):
        if pockets == 0:
            return 0, []

        versions_compartment = versions[0:pockets]
        version_values_compartment = version_values[0:pockets]
        compartment_sum = sum(version_values_compartment)
        current_starting_index = 0

        if compartment_sum < limit_max:
            for i in range(pockets, len(versions)):
                compartment_sum += version_values[i] - version_values_compartment[0]
                del versions_compartment[0]
                del version_values_compartment[0]
                current_starting_index = i - pockets + 1
                versions_compartment.append(versions[i])
                version_values_compartment.append(version_values[i])

                if compartment_sum >= limit_max:
                    break

        stopping_index = 0
        for i in range(len(version_values_compartment)):
            index = current_starting_index + i

            if index - 1 >= stopping_index:
                new_value_index = None
                for j in range(index - 1, stopping_index - 1, -1):
                    if (
                        limit_max
                        <= compartment_sum
                        - version_values_compartment[i]
                        + version_values[j]
                        <= compartment_sum
                    ):
                        new_value_index = j
                    else:
                        if j != index - 1:
                            break
                if new_value_index is not None:
                    compartment_sum = (
                        compartment_sum
                        - version_values_compartment[i]
                        + version_values[new_value_index]
                    )
                    versions_compartment[i] = versions[new_value_index]
                    version_values_compartment[i] = version_values[new_value_index]
                    stopping_index = new_value_index + 1  # noqa
                else:
                    break
            else:
                break

        return self.calculate_versions_used(
            version_to_quantity_mapping, versions_compartment
        )

    def get_versions_to_split_the_biggest(
        self,
        version_to_quantity_mapping: dict[str, int],
        versions: list[str],
        version_values: list[int],
        pockets: int,
        number_of_versions_to_split: int,
        limit_max: int,
    ):
        """
        Uses biggest versions always and ignore limit_max. We do not need to care about it,
         as it will be split more in next step.
        """
        if number_of_versions_to_split:
            biggest_version_values_to_split = version_values[
                -number_of_versions_to_split:
            ]
            limit_max_left = limit_max - sum(biggest_version_values_to_split)
            number_of_pieces_used, version_values_tuple = (
                self.get_versions_to_split_average(
                    version_to_quantity_mapping,
                    versions[:-number_of_versions_to_split],
                    version_values[:-number_of_versions_to_split],
                    pockets - number_of_versions_to_split,
                    limit_max_left,
                    0,
                )
            )
            if number_of_pieces_used >= limit_max_left:
                return self.calculate_versions_used(
                    version_to_quantity_mapping,
                    [version_tuple[0] for version_tuple in version_values_tuple]
                    + versions[-number_of_versions_to_split:],
                )
        return self.get_versions_to_split_average(
            version_to_quantity_mapping,
            versions,
            version_values,
            pockets,
            number_of_versions_to_split,
            limit_max,
        )

    def check_solutions(self):
        valid_solutions = []
        for solution in self.calculated_solutions:
            solution_version_to_quantity_mapping = defaultdict(int)
            failed = False
            for line_config_index, line_config_solution in enumerate(
                solution.line_versions_tuple_list
            ):
                line_config = self.line_configs[line_config_index]
                line_config_sum = 0

                for line_solution in line_config_solution:
                    line_sum = 0
                    for version_id, count in line_solution:
                        solution_version_to_quantity_mapping[version_id] += count
                        line_sum += count
                    line_config_sum += line_sum

                    if line_sum < line_config.min_quantity_per_line:
                        failed = True

                if line_config_sum > line_config.max_quantity_all_lines:
                    failed = True

            if (
                solution_version_to_quantity_mapping == self.version_to_quantity_mapping
                and not failed
            ):
                valid_solutions.append(solution)

        self.calculated_solutions = valid_solutions

    @staticmethod
    def is_line_config_valid(
        number_of_used_pieces,
        number_of_pockets_to_use,
        version_values_tuple,
        current_line_config,
    ):
        # TODO modify check constraint to remember about grouped lines
        # Check number of versions constraint
        if len(version_values_tuple) != number_of_pockets_to_use:
            return False

        # Check max constraint
        if number_of_used_pieces > current_line_config.max_quantity_all_lines:
            return False

        # Check min constraint
        if current_line_config.min_quantity_per_line > number_of_used_pieces:
            return False

        return True

    @staticmethod
    def calculate_versions_used(version_to_quantity_mapping, versions):
        pieces_sum = 0
        version_values_tuple = []
        for version_id in versions:
            pieces_sum += version_to_quantity_mapping[version_id]
            version_values_tuple.append(
                (version_id, version_to_quantity_mapping[version_id])
            )
        return pieces_sum, version_values_tuple

    @staticmethod
    def _sort_versions_by_quantity(versions: list[Version]) -> list[Version]:
        return sorted(versions, key=lambda version: version.quantity)

    @staticmethod
    def _sort_versions_by_pieces_used(version_to_quantity_mapping: dict[str, int]):
        result_tuple = sorted(version_to_quantity_mapping.items(), key=lambda x: x[1])
        return [version_tuple[0] for version_tuple in result_tuple], result_tuple

    def _merge_line_configurations_by_max_limit(self):
        line_config_map = {}
        for line in self.co_mail_facility.lines:
            if line.line_configuration.pk not in line_config_map:
                line_config_map[line.line_configuration.pk] = self.LineConfig(
                    pockets=line.line_configuration.pockets,
                    min_quantity_per_line=line.line_configuration.min_quantity_per_line,
                    max_quantity_all_lines=line.line_configuration.max_quantity_all_lines,
                    size=0,
                )
            line_config_map[line.line_configuration.pk].size += 1

        return self._sort_line_configs_by_pockets(
            line_config_map.values(), reverse=False
        )

    @staticmethod
    def _sort_line_configs_by_pockets(
        line_configs: list["LineConfig"], reverse: bool = False
    ):
        return sorted(
            line_configs,
            key=lambda lc: (lc.pockets, lc.max_quantity_all_lines),
            reverse=reverse,
        )

    @dataclass
    class LineConfig:
        pockets: int
        min_quantity_per_line: int
        max_quantity_all_lines: int
        size: int

    class VersionsToSplitStrategy:
        AVERAGE_VERSIONS = "AVERAGE"
        BIGGEST_VERSIONS = "BIGGEST"


class SolutionChecker:

    def __init__(
        self,
        split_versions_solutions: list[SplitVersionsSolution],
        address_mapping,
        line_configs,
    ):
        self.split_versions_solutions = split_versions_solutions
        self.address_mapping = address_mapping
        self.line_configs = line_configs

    def calculate_solutions(self):
        print("Calculating solutions \n")
        best_solution = 0
        best_version_solution = None
        for solution in self.split_versions_solutions:
            all_lines_result_tuples = []
            # print(f"Splitting versions for: {valid_result}")
            for i, line_result_tuple in enumerate(solution.line_versions_tuple_list):
                all_lines_result_tuples.append(line_result_tuple)

            final_solution = self.calculate_final_solution(all_lines_result_tuples)
            print(f"{final_solution} | {solution}\n")

            if final_solution > best_solution:
                best_solution = final_solution
                best_version_solution = all_lines_result_tuples

        print(f"------- BEST SOLUTION: {best_solution}")
        print(best_version_solution)

    def calculate_final_solution(self, all_lines_result_tuples):
        new_address_mapping = deepcopy(self.address_mapping)
        number_of_packages = 0

        # Reversed because we want to calculate it from the biggest pocket's line
        for lines_result_tuple in reversed(all_lines_result_tuples):
            for line_result_tuple in lines_result_tuple:

                new_new_address_mapping = {}
                line_result_versions_mapping = {
                    lt[0]: lt[1] for lt in line_result_tuple
                }
                for zip_code, versions in new_address_mapping.items():
                    pieces_count = 0
                    inner_mapping = defaultdict(int)
                    new_versions = []

                    for version in versions:
                        if (
                            version in line_result_versions_mapping
                            and line_result_versions_mapping[version]
                            - inner_mapping[version]
                            > 0
                        ):
                            pieces_count += 1
                            inner_mapping[version] += 1
                        else:
                            new_versions.append(version)

                    if pieces_count / 10 >= 1:
                        for version, count in inner_mapping.items():
                            line_result_versions_mapping[version] -= count
                        number_of_packages += 1

                    new_new_address_mapping[zip_code] = new_versions

                new_address_mapping = new_new_address_mapping

        return number_of_packages


def run():
    line_config_51 = LineConfiguration(
        pk=1,
        pockets=51,
        min_quantity_per_line=100_000,
        max_quantity_all_lines=3_500_000,
    )
    line_config_40 = LineConfiguration(
        pk=2,
        pockets=40,
        min_quantity_per_line=100_000,
        max_quantity_all_lines=3_500_000,
    )
    line_config_30 = LineConfiguration(
        pk=3,
        pockets=30,
        min_quantity_per_line=150_000,
        max_quantity_all_lines=15_000_000,
    )
    co_mail_facility = CoMailFacility(
        line_configs=[line_config_51, line_config_40, line_config_30],
        lines=[
            Line(
                line_configuration=line_config_51,
            ),
            Line(
                line_configuration=line_config_40,
            ),
            Line(
                line_configuration=line_config_30,
            ),
        ],
    )

    versions, address_mapping = get_versions(["10mln-prod.csv"])
    start = time.time()
    generator = SplitVersionsGenerator(co_mail_facility, versions)
    solutions = generator.generate(5)
    end = time.time()
    print(f"{end - start} seconds")
    print(len(solutions))

    start = time.time()
    SolutionChecker(
        solutions, address_mapping, generator.line_configs
    ).calculate_solutions()
    end = time.time()
    print(f"{end - start} seconds")


if __name__ == "__main__":
    run()
