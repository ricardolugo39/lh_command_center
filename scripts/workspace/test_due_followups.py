from pprint import pprint

from app.workspace.repositories.followup_repository import (
    FollowupRepository,
)


def main():

    pprint(
        FollowupRepository.list_due_followups()
    )


if __name__ == "__main__":
    main()