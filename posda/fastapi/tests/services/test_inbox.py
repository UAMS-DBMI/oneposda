from papi.services import inbox

USER = "inbox-test-user"
OTHER = "inbox-test-other"


async def seed(conn) -> int:
    for name in (USER, OTHER):
        await conn.execute(
            "insert into user_inbox (user_name, user_email_addr) values ($1, $2) "
            "on conflict (user_name) do nothing",
            name,
            f"{name}@example.invalid",
        )
    file_id = await conn.fetchval("select min(file_id) from file")
    invocation_id = await conn.fetchval(
        "insert into subprocess_invocation (invoking_user, when_invoked, operation_name) "
        "values ($1, now(), 'TestOp') returning subprocess_invocation_id",
        USER,
    )
    bg_id = await conn.fetchval(
        "insert into background_subprocess (subprocess_invocation_id, when_script_started) "
        "values ($1, now()) returning background_subprocess_id",
        invocation_id,
    )
    report_id = await conn.fetchval(
        "insert into background_subprocess_report (background_subprocess_id, file_id, name) "
        "values ($1, $2, 'Email') returning background_subprocess_report_id",
        bg_id,
        file_id,
    )
    return await conn.fetchval(
        """
        insert into user_inbox_content
          (user_inbox_id, background_subprocess_report_id, current_status, statuts_note,
           date_entered)
        values ((select user_inbox_id from user_inbox where user_name = $1), $2, 'entered',
                'created by test', now())
        returning user_inbox_content_id
        """,
        USER,
        report_id,
    )


async def test_list_unread_read_and_dismiss(conn) -> None:
    item_id = await seed(conn)
    assert await inbox.unread_count(conn, USER) == 1
    items = await inbox.list_items(conn, USER)
    assert [i.user_inbox_content_id for i in items] == [item_id]
    assert items[0].operation_name == "TestOp"

    await inbox.mark_read(conn, USER, item_id)
    assert await inbox.unread_count(conn, USER) == 0
    detail = await inbox.get_item(conn, USER, item_id)
    assert detail.current_status == "read"
    assert detail.filed_activity_id is None

    await inbox.dismiss(conn, USER, item_id)
    assert await inbox.list_items(conn, USER) == []
    assert len(await inbox.list_items(conn, USER, include_dismissed=True)) == 1
    ops = [o.operation_type for o in await inbox.recent_operations(conn, item_id)]
    assert ops[:2] == ["message dismissed", "message read"]


async def test_file_and_forward(conn) -> None:
    item_id = await seed(conn)
    await inbox.file_to_activity(conn, USER, item_id, 1)
    detail = await inbox.get_item(conn, USER, item_id)
    assert detail.filed_activity_id == 1
    assert detail.date_dismissed is not None

    new_id = await inbox.forward(conn, USER, detail, OTHER)
    forwarded = await inbox.get_item(conn, OTHER, new_id)
    assert forwarded.background_subprocess_report_id == detail.background_subprocess_report_id
    assert forwarded.current_status == "entered"
    assert OTHER in await inbox.usernames(conn)


async def test_other_users_items_are_invisible(conn) -> None:
    item_id = await seed(conn)
    import pytest

    with pytest.raises(inbox.InboxItemNotFound):
        await inbox.get_item(conn, OTHER, item_id)
