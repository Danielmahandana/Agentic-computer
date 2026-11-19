import asyncio

from computer_agent.computer.session import open_demo_computer


def test_observation_lists_visible_controls_by_role_and_name() -> None:
    async def observe_demo_page() -> None:
        async with open_demo_computer() as computer:
            observation = await computer.observe()

        controls_by_name = {
            control.accessible_name: control
            for control in observation.interactive_elements
        }

        search_box = controls_by_name["Search query"]
        assert search_box.role == "textbox"
        assert search_box.tag == "input"
        assert not search_box.disabled

        search_button = controls_by_name["Search"]
        assert search_button.role == "button"
        assert not search_button.disabled

        details_link = controls_by_name["Open details"]
        assert details_link.role == "link"

        disabled_button = controls_by_name["Disabled action"]
        assert disabled_button.role == "button"
        assert disabled_button.disabled

        labelled_button = controls_by_name["Refresh results"]
        assert labelled_button.role == "button"
        assert labelled_button.disabled

        unnamed_box = next(
            control
            for control in observation.interactive_elements
            if control.tag == "input" and control.accessible_name is None
        )
        assert unnamed_box.role == "textbox"
        assert "Hidden action" not in controls_by_name
        assert "Hidden from assistive technology" not in controls_by_name

    asyncio.run(observe_demo_page())
