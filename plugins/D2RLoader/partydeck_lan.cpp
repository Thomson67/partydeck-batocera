#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <D2RLPlugin/api.h>
#include <cstring>
#include <initializer_list>

namespace {
using namespace D2RL;

constexpr PluginInfo Info{
    .infoSize = PluginInfoSize,
    .abiVersion = D2RL_PLUGIN_ABI_VERSION,
    .id = "partydeck-lan",
    .name = "PartyDeck LAN",
    .version = "0.1.0",
    .author = "PartyDeck",
    .description = "Host or join a private LAN game from the Multiplayer menu.",
    .flags = PluginFlags::Client,
    .reserved = {},
};
constexpr auto Panel = "D2RLoaderMultiplayerPanel";
constexpr auto Channel = "D2RLoaderMultiplayerPanelMessage";
constexpr auto WidgetSuccess = Widgets::Result::Success;

const ThreadService* threads;
const WidgetService* widgets;
bool host;
bool in_game;
bool queued;
char address[16];
wchar_t ready_path[1024];
ULONGLONG deadline;
ULONGLONG next_tick;

enum class Step { Idle, Opened, HostOptions, JoinOptions };
Step step = Step::Idle;

bool same(const char* lhs, const char* rhs) noexcept {
    return lhs && std::strcmp(lhs, rhs) == 0;
}

bool action(const PluginContext* ctx, const char* command) noexcept {
    const Widgets::UiAction message{
        .structSize = Widgets::UiActionSize,
        .flags = 0,
        .target = Channel,
        .command = command,
        .text = "",
    };
    return widgets->dispatchUiAction(ctx, &message) == WidgetSuccess;
}

void tick(const PluginContext*, void*) noexcept;

void queue(const PluginContext* ctx) noexcept {
    if (!queued && step != Step::Idle)
        queued = threads->runOnUiThread(ctx, tick, nullptr) == Threads::Result::Success;
}

void tick(const PluginContext* ctx, void*) noexcept {
    queued = false;
    if (step == Step::Idle || in_game)
        return;
    const ULONGLONG now = GetTickCount64();
    if (now < next_tick) {
        queue(ctx);
        return;
    }
    next_tick = now + 250;

    // Guests wait for PartyDeck to observe the actual host listening socket.
    if (step == Step::Opened && !host && GetFileAttributesW(ready_path) == INVALID_FILE_ATTRIBUTES) {
        queue(ctx);
        return;
    }
    Widgets::WidgetHandle panel{};
    if (widgets->findPanel(ctx, Panel, &panel) == WidgetSuccess) {
        if (step == Step::Opened) {
            step = host ? Step::HostOptions : Step::JoinOptions;
            deadline = now + 8000;
            if (action(ctx, host ? "ShowHost" : "OpenDirectJoin")) {
                queue(ctx);
                return;
            }
        } else if (step == Step::HostOptions) {
            step = Step::Idle;
            if (action(ctx, "CreateGame")) {
                ctx->LogInfo("PartyDeck LAN: requested a LAN Only game.");
                return;
            }
        } else {
            Widgets::WidgetHandle field{};
            char input[64]{};
            uint32_t size{};
            // The session's state.json pre-fills the address. Verify the
            // native dialog has loaded it before sending a join request.
            if (widgets->findWidget(ctx, panel, "DirectJoinAddressInput", &field) == WidgetSuccess
                && widgets->getInputText(ctx, field, input, sizeof(input), &size) == WidgetSuccess
                && same(input, address)) {
                step = Step::Idle;
                if (action(ctx, "JoinDirect")) {
                    ctx->LogInfo("PartyDeck LAN: requested to join P1.");
                    return;
                }
            } else if (now < deadline) {
                queue(ctx);
                return;
            }
        }
    } else if (now < deadline) {
        queue(ctx);
        return;
    }
    step = Step::Idle;
    ctx->LogWarn("PartyDeck LAN: the menu could not be automated. Continue manually.");
}

SharedEvents::UiMessageAction on_message(const PluginContext* ctx, const SharedEvents::UiMessageEvent* event,
                                         void*) noexcept {
    if (same(event->target, "PanelManager") && same(event->text, Panel)) {
        if (same(event->command, "OpenPanel") && !in_game && step == Step::Idle) {
            step = Step::Opened;
            next_tick = GetTickCount64() + 250;
            deadline = next_tick + 8000;
            queue(ctx);
        } else if (same(event->command, "ClosePanel")) {
            step = Step::Idle;
        }
    } else if (same(event->target, Channel)
               && (same(event->command, "Close") || same(event->command, "CloseDirectJoin")
                   || same(event->command, "CancelDirectJoin"))) {
        step = Step::Idle;
    }
    return SharedEvents::UiMessageAction::Continue;
}

void gameplay(const PluginContext*, const Lifecycle::GameplayEvent* event, void*) noexcept {
    in_game = event->kind == Lifecycle::GameplayEventKind::GameJoined;
    step = Step::Idle;
}
} // namespace

D2RL_PLUGIN_EXPORT auto D2RLoaderGetPluginInfo() noexcept -> const D2RL::PluginInfo* {
    return &Info;
}

D2RL_PLUGIN_EXPORT bool D2RLoaderLoadPlugin(const D2RL::PluginContext* ctx) noexcept {
    char local[16]{};
    DWORD length = GetEnvironmentVariableA("PARTYDECK_D2R_HOST", address, sizeof(address));
    if (!length || length >= sizeof(address))
        return false;
    length = GetEnvironmentVariableA("PARTYDECK_PRIVATE_LAN_IP", local, sizeof(local));
    if (!length || length >= sizeof(local))
        return false;
    host = same(local, address);
    if (!host) {
        length = GetEnvironmentVariableW(L"PARTYDECK_D2R_READY", ready_path, 1024);
        if (!length || length >= 1024)
            return false;
    }

    const LifecycleService* lifecycle{};
    const SharedEventService* events{};
    if (ctx->QueryService(&threads) != ServiceQueryResult::Success
        || ctx->QueryService(&widgets) != ServiceQueryResult::Success
        || ctx->QueryService(&lifecycle) != ServiceQueryResult::Success
        || ctx->QueryService(&events) != ServiceQueryResult::Success
        || !HasThreadServiceField(threads, ThreadServiceRequiredSize)
        || !HasWidgetServiceField(widgets, WidgetServiceRequiredSize)
        || !HasLifecycleServiceField(lifecycle, LifecycleServiceRequiredSize)
        || !HasSharedEventServiceField(events, SharedEventServiceRequiredSize)) {
        ctx->LogWarn("PartyDeck LAN: required SDK services are unavailable.");
        return false;
    }
    for (const auto kind : {Lifecycle::GameplayEventKind::GameJoined, Lifecycle::GameplayEventKind::GameLeft}) {
        Lifecycle::GameplayEventListener listener{};
        listener.structSize = sizeof(listener);
        listener.kind = kind;
        listener.callback = gameplay;
        Lifecycle::ListenerHandle handle{};
        if (lifecycle->registerGameplayEventListener(ctx, &listener, &handle) != Lifecycle::Result::Success)
            return false;
    }
    SharedEvents::UiMessageListener listener{};
    listener.structSize = sizeof(listener);
    listener.callback = on_message;
    SharedEvents::ListenerHandle handle{};
    return events->registerUiMessageListener(ctx, &listener, &handle) == SharedEvents::Result::Success;
}

D2RL_PLUGIN_EXPORT void D2RLoaderUnloadPlugin() noexcept {}
