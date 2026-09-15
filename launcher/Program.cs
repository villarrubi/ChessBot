using System.ComponentModel;
using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace ChessBotLauncher;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm(FindProjectRoot(args)));
    }

    private static string FindProjectRoot(string[] args)
    {
        IEnumerable<string> candidates = args
            .Where(Directory.Exists)
            .Concat([Environment.CurrentDirectory, AppContext.BaseDirectory]);
        foreach (string candidate in candidates)
        {
            DirectoryInfo? directory = new(Path.GetFullPath(candidate));
            while (directory is not null)
            {
                if (File.Exists(Path.Combine(directory.FullName, "CMakeLists.txt")) &&
                    Directory.Exists(Path.Combine(directory.FullName, "tools")))
                    return directory.FullName;
                directory = directory.Parent;
            }
        }
        MessageBox.Show("No se ha encontrado la carpeta del proyecto ChessBot.", "ChessBot",
                        MessageBoxButtons.OK, MessageBoxIcon.Error);
        return Environment.CurrentDirectory;
    }
}

internal sealed class MainForm : Form
{
    private readonly string root;
    private readonly string engine;
    private readonly string python;
    private readonly ChessBoard board = new() { Dock = DockStyle.Fill };
    private readonly Label gameStatus = new() { AutoSize = true, Text = "Preparando partida…" };
    private readonly ComboBox playerColor = new() { DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly NumericUpDown thinkTime = new() { Minimum = 100, Maximum = 10000, Value = 750, Increment = 100 };
    private readonly RichTextBox log = new() { Dock = DockStyle.Fill, MinimumSize = new Size(100, 130), ReadOnly = true, BackColor = Color.FromArgb(24, 26, 31), ForeColor = Color.Gainsboro, Font = new Font("Consolas", 9.5f) };
    private readonly ToolTip tips = new() { AutoPopDelay = 12000, InitialDelay = 300, ReshowDelay = 100 };
    private readonly Button cancelButton = new() { Text = "Cancelar tarea", Enabled = false, AutoSize = true };
    private readonly TextBox dataset = new() { Dock = DockStyle.Fill };
    private readonly TextBox trainingOutput = new() { Dock = DockStyle.Fill };
    private readonly TextBox version = new() { Text = "mi-nnue-v1", Dock = DockStyle.Fill };
    private readonly NumericUpDown hidden = new() { Minimum = 1, Maximum = 64, Value = 32 };
    private readonly NumericUpDown epochs = new() { Minimum = 1, Maximum = 10000, Value = 20 };
    private readonly ComboBox generationMode = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 340 };
    private readonly TextBox opponentEngine = new() { Dock = DockStyle.Fill, Enabled = false };
    private readonly NumericUpDown selfplayGames = new() { Minimum = 20, Maximum = 10000, Value = 100, Increment = 2 };
    private readonly NumericUpDown evaluationGames = new() { Minimum = 2, Maximum = 10000, Value = 20, Increment = 2 };
    private readonly NumericUpDown searchDepth = new() { Minimum = 1, Maximum = 12, Value = 3 };
    private readonly NumericUpDown maxPlies = new() { Minimum = 20, Maximum = 1000, Value = 160, Increment = 10 };
    private readonly NumericUpDown maxMinutes = new() { Minimum = 1, Maximum = 10080, Value = 60 };
    private readonly ComboBox trainingTarget = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 290 };
    private readonly TextBox cycleConfig = new() { Dock = DockStyle.Fill };
    private readonly TextBox cycleOutput = new() { Dock = DockStyle.Fill };
    private Process? activeProcess;
    private readonly List<string> moves = [];
    private HashSet<string> legalMoves = [];
    private string? selectedSquare;
    private bool gameBusy;
    private string currentFen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

    public MainForm(string projectRoot)
    {
        root = projectRoot;
        engine = Path.Combine(root, "build", "Release", "chessbot.exe");
        python = Path.Combine(root, ".venv", "Scripts", "python.exe");
        Text = "ChessBot";
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(900, 690);
        Size = new Size(1040, 760);
        Font = new Font("Segoe UI", 10f);
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath) ?? SystemIcons.Application;

        dataset.Text = Path.Combine(root, "build", "phase8-dataset.csv");
        trainingOutput.Text = NewOutput("entrenamiento");
        cycleConfig.Text = Path.Combine(root, "data", "training", "phase10-config-v1.json");
        cycleOutput.Text = NewOutput("ciclo");
        playerColor.Items.AddRange(["Blancas", "Negras"]);
        playerColor.SelectedIndex = 0;
        generationMode.Items.AddRange(["Autojuego: ChessBot contra sí mismo", "Partidas contra otro motor UCI"]);
        generationMode.SelectedIndex = 0;
        generationMode.SelectedIndexChanged += (_, _) => opponentEngine.Enabled = generationMode.SelectedIndex == 1;
        trainingTarget.Items.AddRange(["Solo resultado de las partidas", "Mixto: resultado y evaluación manual", "Evaluación de búsqueda"]);
        trainingTarget.SelectedIndex = 0;
        tips.SetToolTip(dataset, "Tabla de posiciones usada por el entrenamiento directo. El ciclo completo la crea automáticamente con sus partidas nuevas.");
        tips.SetToolTip(hidden, "Tamaño de la capa oculta. 16 o 32 es una buena base; 64 necesita más partidas y reduce la velocidad del motor.");
        tips.SetToolTip(epochs, "Número de pasadas sobre el dataset. Más épocas no compensan pocos datos y pueden sobreajustar.");
        tips.SetToolTip(selfplayGames, "Partidas nuevas que generarán los datos de aprendizaje. Se ejecutan por parejas con colores invertidos.");
        tips.SetToolTip(evaluationGames, "Partidas independientes para decidir si la red nueva es mejor que la referencia.");
        tips.SetToolTip(searchDepth, "Profundidad usada para cada jugada. Una profundidad mayor mejora las partidas, pero multiplica el tiempo necesario.");
        tips.SetToolTip(maxPlies, "Límite de medias jugadas por partida; 160 plies equivalen a 80 movimientos completos.");
        tips.SetToolTip(trainingTarget, "Resultado aprende solo de victoria/tablas/derrota. Mixto añade la evaluación manual y converge con menos partidas.");

        TabControl tabs = new() { Dock = DockStyle.Fill };
        tabs.TabPages.Add(BuildPlayTab());
        tabs.TabPages.Add(BuildTrainingTab());
        tabs.TabPages.Add(BuildToolsTab());
        Controls.Add(tabs);
        board.SquareClicked += OnBoardClick;
        cancelButton.Click += (_, _) => CancelActiveTask();
        Shown += async (_, _) => await NewGameAsync();
        FormClosing += (_, _) => CancelActiveTask();
        FormClosed += (_, _) => tips.Dispose();
    }

    private TabPage BuildPlayTab()
    {
        TabPage page = new("Jugar");
        TableLayoutPanel layout = new() { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1, Padding = new Padding(14) };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 67));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33));
        layout.Controls.Add(board, 0, 0);

        FlowLayoutPanel side = new() { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, Padding = new Padding(12), AutoScroll = true };
        Label title = new() { Text = "Partida contra ChessBot", AutoSize = true, Font = new Font(Font, FontStyle.Bold) };
        Button newGame = new() { Text = "Nueva partida", AutoSize = true };
        newGame.Click += async (_, _) => await NewGameAsync();
        side.Controls.Add(title);
        side.Controls.Add(Spacer());
        side.Controls.Add(new Label { Text = "Tu color", AutoSize = true });
        side.Controls.Add(playerColor);
        side.Controls.Add(new Label { Text = "Tiempo del motor (ms)", AutoSize = true, Margin = new Padding(3, 12, 3, 3) });
        side.Controls.Add(thinkTime);
        side.Controls.Add(newGame);
        side.Controls.Add(Spacer());
        side.Controls.Add(gameStatus);
        side.Controls.Add(new Label { Text = "Selecciona una pieza y después su casilla de destino. Las promociones se realizan a dama.", MaximumSize = new Size(260, 0), AutoSize = true, ForeColor = Color.DimGray, Margin = new Padding(3, 18, 3, 3) });
        layout.Controls.Add(side, 1, 0);
        page.Controls.Add(layout);
        return page;
    }

    private TabPage BuildTrainingTab()
    {
        TabPage page = new("Entrenar");
        TableLayoutPanel outer = new() { Dock = DockStyle.Fill, RowCount = 3, Padding = new Padding(14) };
        outer.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        outer.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        outer.RowStyles.Add(new RowStyle(SizeType.Absolute, 160));
        Label explanation = new()
        {
            AutoSize = true,
            MaximumSize = new Size(940, 0),
            Margin = new Padding(0, 0, 0, 12),
            Text = "El ciclo completo genera partidas nuevas, extrae sus posiciones a un dataset, entrena una red y la enfrenta a la referencia. " +
                   "Elige autojuego o un ejecutable UCI rival. Pasa el ratón sobre cada parámetro para ver su explicación."
        };
        TableLayoutPanel form = new() { Dock = DockStyle.Top, AutoSize = true, ColumnCount = 3, Padding = new Padding(0, 0, 0, 12) };
        form.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        form.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        form.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        for (int row = 0; row < 12; ++row)
        {
            form.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        }

        AddPathRow(form, 0, "Dataset existente", dataset, "Examinar…", () => ChooseFile(dataset, "CSV o Parquet|*.csv;*.parquet|Todos|*.*"));
        AddPathRow(form, 1, "Salida red", trainingOutput, "Elegir…", () => ChooseFolder(trainingOutput));
        AddFieldRow(form, 2, "Versión", version);
        FlowLayoutPanel numbers = new() { AutoSize = true, FlowDirection = FlowDirection.LeftToRight };
        numbers.Controls.Add(new Label { Text = "Neuronas", AutoSize = true, Margin = new Padding(0, 7, 5, 0) });
        numbers.Controls.Add(hidden);
        numbers.Controls.Add(new Label { Text = "Épocas", AutoSize = true, Margin = new Padding(18, 7, 5, 0) });
        numbers.Controls.Add(epochs);
        AddFieldRow(form, 3, "Parámetros", numbers);
        AddFieldRow(form, 4, "Origen de partidas", generationMode);
        AddPathRow(form, 5, "Motor rival", opponentEngine, "Examinar…", () => ChooseFile(opponentEngine, "Ejecutable|*.exe|Todos|*.*"));
        FlowLayoutPanel gameCounts = new() { AutoSize = true, FlowDirection = FlowDirection.LeftToRight };
        gameCounts.Controls.Add(new Label { Text = "Para aprender", AutoSize = true, Margin = new Padding(0, 7, 5, 0) });
        gameCounts.Controls.Add(selfplayGames);
        gameCounts.Controls.Add(new Label { Text = "Para evaluar", AutoSize = true, Margin = new Padding(18, 7, 5, 0) });
        gameCounts.Controls.Add(evaluationGames);
        AddFieldRow(form, 6, "Partidas", gameCounts);
        FlowLayoutPanel search = new() { AutoSize = true, FlowDirection = FlowDirection.LeftToRight };
        search.Controls.Add(new Label { Text = "Profundidad", AutoSize = true, Margin = new Padding(0, 7, 5, 0) });
        search.Controls.Add(searchDepth);
        search.Controls.Add(new Label { Text = "Máx. plies", AutoSize = true, Margin = new Padding(18, 7, 5, 0) });
        search.Controls.Add(maxPlies);
        search.Controls.Add(new Label { Text = "Minutos", AutoSize = true, Margin = new Padding(18, 7, 5, 0) });
        search.Controls.Add(maxMinutes);
        AddFieldRow(form, 7, "Búsqueda", search);
        AddFieldRow(form, 8, "Objetivo", trainingTarget);
        AddPathRow(form, 9, "Config. base", cycleConfig, "Examinar…", () => ChooseFile(cycleConfig, "JSON|*.json|Todos|*.*"));
        AddPathRow(form, 10, "Salida ciclo", cycleOutput, "Elegir…", () => ChooseFolder(cycleOutput));

        FlowLayoutPanel actions = new() { AutoSize = true, FlowDirection = FlowDirection.LeftToRight, Margin = new Padding(0, 12, 0, 0) };
        Button train = new() { Text = "Entrenar nueva red", AutoSize = true };
        train.Click += async (_, _) => await TrainAsync();
        Button cycle = new() { Text = "Ejecutar ciclo completo", AutoSize = true };
        cycle.Click += async (_, _) => await RunCycleAsync();
        actions.Controls.Add(train);
        actions.Controls.Add(cycle);
        actions.Controls.Add(cancelButton);
        form.Controls.Add(actions, 1, 11);
        outer.Controls.Add(explanation, 0, 0);
        outer.Controls.Add(form, 0, 1);
        outer.Controls.Add(log, 0, 2);
        page.Controls.Add(outer);
        return page;
    }

    private TabPage BuildToolsTab()
    {
        TabPage page = new("Herramientas");
        TableLayoutPanel layout = new() { Dock = DockStyle.Fill, RowCount = 3, Padding = new Padding(18) };
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        Label state = new() { AutoSize = true, Text = StatusText(), MaximumSize = new Size(850, 0) };
        FlowLayoutPanel buttons = new() { AutoSize = true, FlowDirection = FlowDirection.LeftToRight, Margin = new Padding(0, 16, 0, 16) };
        Button benchmark = new() { Text = "Benchmark rápido", AutoSize = true };
        benchmark.Click += async (_, _) => await RunTaskAsync(engine, ["bench", "5"], "Benchmark");
        Button build = new() { Text = "Compilar/actualizar", AutoSize = true };
        build.Click += async (_, _) => await BuildEngineAsync();
        Button results = new() { Text = "Abrir resultados", AutoSize = true };
        results.Click += (_, _) => OpenFolder(Path.Combine(root, "build"));
        Button project = new() { Text = "Abrir proyecto", AutoSize = true };
        project.Click += (_, _) => OpenFolder(root);
        buttons.Controls.AddRange([benchmark, build, results, project]);
        layout.Controls.Add(state, 0, 0);
        layout.Controls.Add(buttons, 0, 1);
        layout.Controls.Add(new RichTextBox
        {
            Dock = DockStyle.Fill,
            ReadOnly = true,
            Text =
            "El ejecutable del motor se encuentra en:\n" + engine +
            "\n\nEl lanzador oculta los procesos de consola y muestra su resultado dentro de la aplicación. " +
            "Para usar ChessBot con Arena, Cute Chess u otra interfaz UCI, selecciona chessbot.exe como motor."
        }, 0, 2);
        page.Controls.Add(layout);
        return page;
    }

    private async Task NewGameAsync()
    {
        moves.Clear();
        selectedSquare = null;
        currentFen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
        board.Position = currentFen;
        board.SelectedSquare = null;
        board.Flipped = playerColor.SelectedIndex == 1;
        board.Invalidate();
        if (!File.Exists(engine))
        {
            gameStatus.Text = "Falta el motor. Usa Herramientas → Compilar/actualizar.";
            return;
        }
        await RefreshPositionAsync();
        if (playerColor.SelectedIndex == 1)
            await EngineMoveAsync();
    }

    private async void OnBoardClick(object? sender, string square)
    {
        if (gameBusy || SideToMoveIsWhite() != PlayerIsWhite())
            return;
        string piece = board.PieceAt(square);
        if (selectedSquare is null)
        {
            if (piece.Length > 0 && char.IsUpper(piece[0]) == PlayerIsWhite())
            {
                selectedSquare = square;
                board.SelectedSquare = square;
                board.TargetSquares = legalMoves.Where(move => move.StartsWith(square, StringComparison.Ordinal)).Select(move => move[2..4]).ToHashSet();
                board.Invalidate();
            }
            return;
        }

        string prefix = selectedSquare + square;
        string? move = legalMoves.FirstOrDefault(candidate => candidate == prefix + "q") ??
                       legalMoves.FirstOrDefault(candidate => candidate.StartsWith(prefix, StringComparison.Ordinal));
        if (move is null)
        {
            selectedSquare = null;
            board.SelectedSquare = null;
            board.TargetSquares.Clear();
            board.Invalidate();
            OnBoardClick(sender, square);
            return;
        }

        moves.Add(move);
        selectedSquare = null;
        board.SelectedSquare = null;
        board.TargetSquares.Clear();
        await RefreshPositionAsync();
        if (legalMoves.Count > 0)
            await EngineMoveAsync();
    }

    private async Task RefreshPositionAsync()
    {
        gameBusy = true;
        try
        {
            List<string> arguments = ["inspect"];
            if (moves.Count > 0)
            {
                arguments.Add("--moves");
                arguments.Add(string.Join(' ', moves));
            }
            string output = await CaptureAsync(engine, arguments);
            using JsonDocument document = JsonDocument.Parse(output);
            JsonElement rootElement = document.RootElement;
            currentFen = rootElement.GetProperty("fen").GetString() ?? currentFen;
            legalMoves = rootElement.GetProperty("legal_moves").EnumerateArray()
                .Select(value => value.GetString() ?? string.Empty).Where(value => value.Length >= 4).ToHashSet();
            string status = rootElement.GetProperty("status").GetString() ?? "ongoing";
            board.Position = currentFen;
            board.Invalidate();
            gameStatus.Text = status == "ongoing"
                ? (SideToMoveIsWhite() ? "Turno de blancas" : "Turno de negras")
                : TranslateStatus(status);
        }
        catch (Exception exception)
        {
            gameStatus.Text = "No se pudo leer la posición: " + exception.Message;
        }
        finally
        {
            gameBusy = false;
        }
    }

    private async Task EngineMoveAsync()
    {
        if (legalMoves.Count == 0 || SideToMoveIsWhite() == PlayerIsWhite())
            return;
        gameBusy = true;
        gameStatus.Text = "ChessBot está pensando…";
        try
        {
            string bestMove = await SearchBestMoveAsync((int)thinkTime.Value);
            if (bestMove is not "(none)" && bestMove.Length >= 4)
                moves.Add(bestMove);
        }
        catch (Exception exception)
        {
            gameStatus.Text = "Error del motor: " + exception.Message;
            gameBusy = false;
            return;
        }
        gameBusy = false;
        await RefreshPositionAsync();
    }

    private async Task<string> SearchBestMoveAsync(int milliseconds)
    {
        ProcessStartInfo start = HiddenProcess(engine);
        using Process process = Process.Start(start) ?? throw new InvalidOperationException("No se pudo iniciar el motor");
        await process.StandardInput.WriteLineAsync("uci");
        await ReadUntilAsync(process, line => line == "uciok");
        await process.StandardInput.WriteLineAsync("isready");
        await ReadUntilAsync(process, line => line == "readyok");
        string position = moves.Count == 0 ? "position startpos" : "position startpos moves " + string.Join(' ', moves);
        await process.StandardInput.WriteLineAsync(position);
        await process.StandardInput.WriteLineAsync($"go movetime {milliseconds}");
        string answer = await ReadUntilAsync(process, line => line.StartsWith("bestmove ", StringComparison.Ordinal));
        await process.StandardInput.WriteLineAsync("quit");
        return answer.Split(' ', StringSplitOptions.RemoveEmptyEntries)[1];
    }

    private static async Task<string> ReadUntilAsync(Process process, Func<string, bool> predicate)
    {
        while (await process.StandardOutput.ReadLineAsync() is { } line)
            if (predicate(line))
                return line;
        string error = await process.StandardError.ReadToEndAsync();
        throw new InvalidOperationException(string.IsNullOrWhiteSpace(error) ? "El motor terminó inesperadamente" : error.Trim());
    }

    private async Task TrainAsync()
    {
        if (!File.Exists(dataset.Text))
        {
            MessageBox.Show("Selecciona un dataset existente.", "Entrenamiento", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        trainingOutput.Text = UniqueOutput(trainingOutput.Text);
        await RunTaskAsync(python,
            ["tools/train_nnue.py", "--dataset", dataset.Text, "--output-dir", trainingOutput.Text,
             "--version", version.Text.Trim(), "--hidden", hidden.Value.ToString(), "--epochs", epochs.Value.ToString(),
             "--target", TargetValue(), "--teacher-weight", "0.25", "--seed", "7"], "Entrenamiento NNUE");
    }

    private async Task RunCycleAsync()
    {
        if (!File.Exists(cycleConfig.Text))
        {
            MessageBox.Show("No se encuentra la configuración del ciclo.", "Ciclo de aprendizaje", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        if (generationMode.SelectedIndex == 1 && !File.Exists(opponentEngine.Text))
        {
            MessageBox.Show("Selecciona el ejecutable UCI del motor rival.", "Ciclo de aprendizaje", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        cycleOutput.Text = UniqueOutput(cycleOutput.Text);
        string generatedConfig;
        try
        {
            generatedConfig = CreateCycleConfig();
        }
        catch (Exception exception)
        {
            MessageBox.Show("No se pudo preparar la configuración: " + exception.Message, "Ciclo de aprendizaje", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        await RunTaskAsync(python,
            ["tools/learning_cycle.py", "--config", generatedConfig, "--engine", engine, "--output-dir", cycleOutput.Text],
            "Ciclo completo");
    }

    private string CreateCycleConfig()
    {
        JsonObject config = JsonNode.Parse(File.ReadAllText(cycleConfig.Text))?.AsObject() ??
                            throw new InvalidDataException("El JSON base está vacío");
        string stamp = DateTime.Now.ToString("yyyyMMdd-HHmmss");
        config["id"] = "launcher-cycle-" + stamp;
        config["candidate_version"] = string.IsNullOrWhiteSpace(version.Text) ? "launcher-nnue-" + stamp : version.Text.Trim();
        config["source_pgns"] = new JsonArray();

        JsonObject budgets = ObjectAt(config, "budgets");
        budgets["selfplay_games"] = EvenCount(selfplayGames.Value);
        budgets["evaluation_games"] = EvenCount(evaluationGames.Value);
        budgets["max_seconds"] = (int)maxMinutes.Value * 60;

        JsonObject selfplay = ObjectAt(config, "selfplay");
        selfplay["enabled"] = true;
        selfplay["depth"] = (int)searchDepth.Value;
        selfplay["max_plies"] = (int)maxPlies.Value;
        if (generationMode.SelectedIndex == 1)
        {
            string opponent = Path.GetFullPath(opponentEngine.Text);
            selfplay["opponent_engine"] = opponent;
            selfplay["opponent_name"] = Path.GetFileNameWithoutExtension(opponent);
            selfplay["opponent_options"] = new JsonObject();
        }
        else
        {
            selfplay.Remove("opponent_engine");
            selfplay.Remove("opponent_name");
            selfplay.Remove("opponent_options");
        }

        JsonObject training = ObjectAt(config, "training");
        training["hidden"] = (int)hidden.Value;
        training["epochs"] = (int)epochs.Value;
        training["target"] = TargetValue();

        JsonObject evaluation = ObjectAt(config, "evaluation");
        evaluation["depth"] = (int)searchDepth.Value;
        evaluation["benchmark_depth"] = Math.Min(12, (int)searchDepth.Value + 1);
        evaluation["max_plies"] = (int)maxPlies.Value;

        string configDirectory = Path.Combine(root, "build", "launcher-configs");
        Directory.CreateDirectory(configDirectory);
        string path = Path.Combine(configDirectory, "cycle-" + stamp + ".json");
        File.WriteAllText(path, config.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + Environment.NewLine);
        return path;
    }

    private string TargetValue() => trainingTarget.SelectedIndex switch
    {
        1 => "mixed",
        2 => "search",
        _ => "result"
    };

    private static int EvenCount(decimal value)
    {
        int count = (int)value;
        return count % 2 == 0 ? count : count + 1;
    }

    private static JsonObject ObjectAt(JsonObject parent, string name)
    {
        if (parent[name] is JsonObject value)
            return value;
        JsonObject created = [];
        parent[name] = created;
        return created;
    }

    private async Task BuildEngineAsync()
    {
        string cmake = Path.Combine(root, ".venv", "Scripts", "cmake.exe");
        if (!File.Exists(cmake))
            cmake = "cmake";
        bool configured = await RunTaskAsync(cmake, ["-S", ".", "-B", "build", "-A", "x64", "-DCHESSBOT_SLOW_TESTS=ON"], "Configurar", false);
        if (configured)
            await RunTaskAsync(cmake, ["--build", "build", "--config", "Release", "--parallel"], "Compilar");
    }

    private async Task<bool> RunTaskAsync(string executable, IReadOnlyList<string> arguments, string name, bool notify = true)
    {
        if (activeProcess is not null)
        {
            MessageBox.Show("Ya hay una tarea en ejecución.", "ChessBot", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return false;
        }
        if (Path.IsPathRooted(executable) && !File.Exists(executable))
        {
            MessageBox.Show("No se encuentra: " + executable, "ChessBot", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return false;
        }
        AppendLog($"\n[{DateTime.Now:HH:mm:ss}] {name}\n");
        ProcessStartInfo start = HiddenProcess(executable);
        foreach (string argument in arguments)
            start.ArgumentList.Add(argument);
        start.WorkingDirectory = root;
        try
        {
            activeProcess = new Process { StartInfo = start, EnableRaisingEvents = true };
            activeProcess.OutputDataReceived += (_, eventArgs) => { if (eventArgs.Data is not null) AppendLog(eventArgs.Data + "\n"); };
            activeProcess.ErrorDataReceived += (_, eventArgs) => { if (eventArgs.Data is not null) AppendLog(eventArgs.Data + "\n"); };
            activeProcess.Start();
            cancelButton.Enabled = true;
            activeProcess.BeginOutputReadLine();
            activeProcess.BeginErrorReadLine();
            await activeProcess.WaitForExitAsync();
            int code = activeProcess.ExitCode;
            AppendLog($"[{DateTime.Now:HH:mm:ss}] {(code == 0 ? "Completado" : "Terminó con error " + code)}\n");
            if (notify)
                MessageBox.Show(code == 0 ? name + " completado." : name + " terminó con errores. Revisa el registro.",
                                "ChessBot", MessageBoxButtons.OK,
                                code == 0 ? MessageBoxIcon.Information : MessageBoxIcon.Error);
            return code == 0;
        }
        catch (Exception exception)
        {
            AppendLog("Error: " + exception.Message + "\n");
            if (notify)
                MessageBox.Show(exception.Message, "ChessBot", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return false;
        }
        finally
        {
            activeProcess?.Dispose();
            activeProcess = null;
            cancelButton.Enabled = false;
        }
    }

    private void CancelActiveTask()
    {
        try
        {
            if (activeProcess is { HasExited: false })
                activeProcess.Kill(true);
        }
        catch
        {
            // The process may finish between the state check and Kill.
        }
    }

    private static ProcessStartInfo HiddenProcess(string executable) => new()
    {
        FileName = executable,
        UseShellExecute = false,
        RedirectStandardInput = true,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
        CreateNoWindow = true,
        StandardOutputEncoding = Encoding.UTF8,
        StandardErrorEncoding = Encoding.UTF8
    };

    private async Task<string> CaptureAsync(string executable, IReadOnlyList<string> arguments)
    {
        ProcessStartInfo start = HiddenProcess(executable);
        start.WorkingDirectory = root;
        foreach (string argument in arguments)
            start.ArgumentList.Add(argument);
        using Process process = Process.Start(start) ?? throw new InvalidOperationException("No se pudo iniciar " + executable);
        string output = await process.StandardOutput.ReadToEndAsync();
        string error = await process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();
        if (process.ExitCode != 0)
            throw new InvalidOperationException(error.Trim());
        return output.Trim();
    }

    private bool PlayerIsWhite() => playerColor.SelectedIndex == 0;
    private bool SideToMoveIsWhite() => currentFen.Split(' ', StringSplitOptions.RemoveEmptyEntries).ElementAtOrDefault(1) == "w";
    private string NewOutput(string prefix) => Path.Combine(root, "build", $"{prefix}-{DateTime.Now:yyyyMMdd-HHmmss}");
    private static string UniqueOutput(string path) => Directory.Exists(path) || File.Exists(path) ? path + "-" + DateTime.Now.ToString("HHmmss") : path;
    private string StatusText() => $"Proyecto: {root}\nMotor: {(File.Exists(engine) ? "listo" : "pendiente de compilar")}\nPython de entrenamiento: {(File.Exists(python) ? "listo" : "no instalado")}";

    private void AppendLog(string text)
    {
        if (InvokeRequired)
        {
            BeginInvoke(() => AppendLog(text));
            return;
        }
        log.AppendText(text);
        log.SelectionStart = log.TextLength;
        log.ScrollToCaret();
    }

    private static string TranslateStatus(string status) => status switch
    {
        "checkmate" => "Jaque mate",
        "stalemate" => "Tablas por ahogado",
        "threefold" => "Tablas por repetición",
        "fifty_move" => "Tablas por cincuenta movimientos",
        "insufficient_material" => "Tablas por material insuficiente",
        _ => "Partida terminada: " + status
    };

    private static Control Spacer() => new Panel { Height = 8, Width = 8 };

    private static void AddPathRow(TableLayoutPanel panel, int row, string label, TextBox box, string buttonText, Action action)
    {
        panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        panel.Controls.Add(new Label { Text = label, AutoSize = true, Anchor = AnchorStyles.Left, Margin = new Padding(0, 8, 12, 8) }, 0, row);
        panel.Controls.Add(box, 1, row);
        Button button = new() { Text = buttonText, AutoSize = true };
        button.Click += (_, _) => action();
        panel.Controls.Add(button, 2, row);
    }

    private static void AddFieldRow(TableLayoutPanel panel, int row, string label, Control control)
    {
        panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        panel.Controls.Add(new Label { Text = label, AutoSize = true, Anchor = AnchorStyles.Left, Margin = new Padding(0, 8, 12, 8) }, 0, row);
        panel.Controls.Add(control, 1, row);
        panel.SetColumnSpan(control, 2);
    }

    private void ChooseFile(TextBox destination, string filter)
    {
        using OpenFileDialog dialog = new() { Filter = filter, CheckFileExists = true, InitialDirectory = root };
        if (dialog.ShowDialog(this) == DialogResult.OK)
            destination.Text = dialog.FileName;
    }

    private void ChooseFolder(TextBox destination)
    {
        using FolderBrowserDialog dialog = new() { InitialDirectory = root };
        if (dialog.ShowDialog(this) == DialogResult.OK)
            destination.Text = Path.Combine(dialog.SelectedPath, "chessbot-" + DateTime.Now.ToString("yyyyMMdd-HHmmss"));
    }

    private static void OpenFolder(string path)
    {
        Directory.CreateDirectory(path);
        Process.Start(new ProcessStartInfo("explorer.exe", path) { UseShellExecute = true });
    }
}

internal sealed class ChessBoard : Control
{
    private static readonly Dictionary<char, string> Symbols = new()
    {
        ['K'] = "♔",
        ['Q'] = "♕",
        ['R'] = "♖",
        ['B'] = "♗",
        ['N'] = "♘",
        ['P'] = "♙",
        ['k'] = "♚",
        ['q'] = "♛",
        ['r'] = "♜",
        ['b'] = "♝",
        ['n'] = "♞",
        ['p'] = "♟"
    };
    private readonly Dictionary<string, char> pieces = [];
    private string position = string.Empty;
    public event EventHandler<string>? SquareClicked;
    [Browsable(false), DesignerSerializationVisibility(DesignerSerializationVisibility.Hidden)]
    public string? SelectedSquare { get; set; }
    [Browsable(false), DesignerSerializationVisibility(DesignerSerializationVisibility.Hidden)]
    public HashSet<string> TargetSquares { get; set; } = [];
    [Browsable(false), DesignerSerializationVisibility(DesignerSerializationVisibility.Hidden)]
    public bool Flipped { get; set; }

    [Browsable(false), DesignerSerializationVisibility(DesignerSerializationVisibility.Hidden)]
    public string Position
    {
        get => position;
        set
        {
            position = value;
            ParseFen(value);
        }
    }

    public ChessBoard()
    {
        DoubleBuffered = true;
        ResizeRedraw = true;
        MinimumSize = new Size(480, 480);
        Cursor = Cursors.Hand;
    }

    public string PieceAt(string square) => pieces.TryGetValue(square, out char piece) ? piece.ToString() : string.Empty;

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        int size = Math.Min(ClientSize.Width, ClientSize.Height) - 16;
        int cell = size / 8;
        int boardSize = cell * 8;
        int left = (ClientSize.Width - boardSize) / 2;
        int top = (ClientSize.Height - boardSize) / 2;
        using Font pieceFont = new("Segoe UI Symbol", cell * 0.62f, FontStyle.Regular, GraphicsUnit.Pixel);
        using Font coordinateFont = new("Segoe UI", Math.Max(8, cell * 0.13f), FontStyle.Bold, GraphicsUnit.Pixel);
        using StringFormat centered = new() { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
        for (int displayRank = 0; displayRank < 8; ++displayRank)
        {
            for (int displayFile = 0; displayFile < 8; ++displayFile)
            {
                int file = Flipped ? 7 - displayFile : displayFile;
                int rank = Flipped ? displayRank : 7 - displayRank;
                string square = $"{(char)('a' + file)}{rank + 1}";
                Rectangle rectangle = new(left + displayFile * cell, top + displayRank * cell, cell, cell);
                bool light = (file + rank) % 2 != 0;
                Color color = light ? Color.FromArgb(235, 220, 184) : Color.FromArgb(119, 149, 86);
                if (square == SelectedSquare)
                    color = Color.FromArgb(246, 246, 105);
                else if (TargetSquares.Contains(square))
                    color = light ? Color.FromArgb(191, 205, 122) : Color.FromArgb(91, 170, 91);
                using SolidBrush background = new(color);
                e.Graphics.FillRectangle(background, rectangle);
                if (pieces.TryGetValue(square, out char piece))
                {
                    using SolidBrush shadow = new(Color.FromArgb(80, Color.Black));
                    Rectangle shadowRect = new(rectangle.X + 2, rectangle.Y + 3, rectangle.Width, rectangle.Height);
                    e.Graphics.DrawString(Symbols[piece], pieceFont, shadow, shadowRect, centered);
                    using SolidBrush foreground = new(char.IsUpper(piece) ? Color.WhiteSmoke : Color.FromArgb(30, 30, 30));
                    e.Graphics.DrawString(Symbols[piece], pieceFont, foreground, rectangle, centered);
                }
                if (displayFile == 0)
                {
                    using SolidBrush brush = new(light ? Color.FromArgb(119, 149, 86) : Color.FromArgb(235, 220, 184));
                    e.Graphics.DrawString((rank + 1).ToString(), coordinateFont, brush, rectangle.X + 3, rectangle.Y + 2);
                }
                if (displayRank == 7)
                {
                    using SolidBrush brush = new(light ? Color.FromArgb(119, 149, 86) : Color.FromArgb(235, 220, 184));
                    e.Graphics.DrawString(((char)('a' + file)).ToString(), coordinateFont, brush, rectangle.Right - coordinateFont.Size - 3, rectangle.Bottom - coordinateFont.Height - 1);
                }
            }
        }
    }

    protected override void OnMouseClick(MouseEventArgs e)
    {
        base.OnMouseClick(e);
        int size = Math.Min(ClientSize.Width, ClientSize.Height) - 16;
        int cell = size / 8;
        int boardSize = cell * 8;
        int left = (ClientSize.Width - boardSize) / 2;
        int top = (ClientSize.Height - boardSize) / 2;
        int displayFile = (e.X - left) / cell;
        int displayRank = (e.Y - top) / cell;
        if (e.X < left || e.Y < top || displayFile is < 0 or > 7 || displayRank is < 0 or > 7)
            return;
        int file = Flipped ? 7 - displayFile : displayFile;
        int rank = Flipped ? displayRank : 7 - displayRank;
        SquareClicked?.Invoke(this, $"{(char)('a' + file)}{rank + 1}");
    }

    private void ParseFen(string fen)
    {
        pieces.Clear();
        string placement = fen.Split(' ', StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? string.Empty;
        string[] ranks = placement.Split('/');
        if (ranks.Length != 8)
            return;
        for (int index = 0; index < 8; ++index)
        {
            int file = 0;
            foreach (char token in ranks[index])
            {
                if (char.IsDigit(token))
                    file += token - '0';
                else if (file < 8)
                    pieces[$"{(char)('a' + file++)}{8 - index}"] = token;
            }
        }
    }
}
