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
    private static readonly Color Paper = Color.FromArgb(244, 241, 233);
    private static readonly Color Ink = Color.FromArgb(39, 49, 48);
    private static readonly Color Accent = Color.FromArgb(42, 79, 70);
    private static readonly Color AccentLight = Color.FromArgb(218, 228, 219);
    private static readonly Color Field = Color.FromArgb(255, 254, 250);
    private readonly string root;
    private readonly string engine;
    private readonly string python;
    private readonly ChessBoard board = new() { Dock = DockStyle.Fill };
    private readonly Label gameStatus = new()
    {
        AutoSize = false,
        Text = "Preparando partida…",
        TextAlign = ContentAlignment.MiddleLeft,
        Padding = new Padding(12, 8, 12, 8),
        Width = 270,
        Height = 52,
        BorderStyle = BorderStyle.FixedSingle,
        Font = new Font("Segoe UI", 10f, FontStyle.Bold)
    };
    private readonly ComboBox playerColor = new() { DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly NumericUpDown thinkTime = new() { Minimum = 100, Maximum = 10000, Value = 750, Increment = 100 };
    private readonly RichTextBox log = new() { Dock = DockStyle.Fill, MinimumSize = new Size(100, 100), ReadOnly = true, BackColor = Color.FromArgb(24, 26, 31), ForeColor = Color.Gainsboro, Font = new Font("Consolas", 9.5f) };
    private readonly ToolTip tips = new() { AutoPopDelay = 12000, InitialDelay = 300, ReshowDelay = 100 };
    private readonly Button cancelButton = new() { Text = "Cancelar tarea", Enabled = false, AutoSize = true };
    private readonly Button resignButton = new() { Text = "Rendirse", AutoSize = true, Enabled = false };
    private readonly TextBox dataset = new() { Dock = DockStyle.Fill };
    private readonly TextBox trainingOutput = new() { Dock = DockStyle.Fill };
    private readonly TextBox version = new() { Text = "SegundoModelo-v2", Dock = DockStyle.Fill };
    private readonly NumericUpDown hidden = new() { Minimum = 2, Maximum = 64, Value = 32 };
    private readonly NumericUpDown epochs = new() { Minimum = 1, Maximum = 10000, Value = 60 };
    private readonly ComboBox generationMode = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 340 };
    private readonly TextBox opponentEngine = new() { Dock = DockStyle.Fill, Enabled = false };
    private readonly NumericUpDown selfplayGames = new() { Minimum = 20, Maximum = 10000, Value = 1000, Increment = 2 };
    private readonly NumericUpDown evaluationGames = new() { Minimum = 2, Maximum = 10000, Value = 100, Increment = 2 };
    private readonly NumericUpDown searchDepth = new() { Minimum = 1, Maximum = 12, Value = 3 };
    private readonly NumericUpDown maxPlies = new() { Minimum = 20, Maximum = 1000, Value = 240, Increment = 10 };
    private readonly NumericUpDown maxMinutes = new() { Minimum = 1, Maximum = 10080, Value = 300 };
    private readonly ComboBox trainingTarget = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 290 };
    private readonly TextBox stockfishEngine = new() { Dock = DockStyle.Fill, Width = 320 };
    private readonly NumericUpDown eloGames = new() { Minimum = 2, Maximum = 1000, Value = 16, Increment = 2 };
    private readonly NumericUpDown eloDepth = new() { Minimum = 1, Maximum = 12, Value = 3 };
    private readonly TextBox customOpening = new() { Dock = DockStyle.Fill };
    private readonly CheckedListBox openingSelection = new()
    {
        CheckOnClick = true,
        MultiColumn = true,
        ColumnWidth = 190,
        Height = 62,
        IntegralHeight = false,
        Dock = DockStyle.Fill
    };
    private readonly TextBox cycleConfig = new() { Dock = DockStyle.Fill };
    private readonly TextBox cycleOutput = new() { Dock = DockStyle.Fill };
    private Process? activeProcess;
    private readonly List<string> moves = [];
    private HashSet<string> legalMoves = [];
    private string? selectedSquare;
    private bool gameBusy;
    private bool gameFinished;
    private string currentFen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

    public MainForm(string projectRoot)
    {
        root = projectRoot;
        engine = Path.Combine(root, "build", "Release", "chessbot.exe");
        python = Path.Combine(root, ".venv", "Scripts", "python.exe");
        Text = "ChessBot — mesa de análisis";
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(900, 690);
        Size = new Size(1040, 760);
        Font = new Font("Segoe UI", 10f);
        BackColor = Paper;
        ForeColor = Ink;
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath) ?? SystemIcons.Application;

        dataset.Text = Path.Combine(root, "build", "phase8-dataset.csv");
        trainingOutput.Text = NewOutput("entrenamiento");
        cycleConfig.Text = Path.Combine(root, "data", "training", "learning-v2.json");
        cycleOutput.Text = NewOutput("ciclo");
        playerColor.Items.AddRange(["Blancas", "Negras"]);
        playerColor.SelectedIndex = 0;
        generationMode.Items.AddRange(["Autojuego: ChessBot contra sí mismo", "Partidas contra otro motor UCI"]);
        generationMode.SelectedIndex = 0;
        generationMode.SelectedIndexChanged += (_, _) => opponentEngine.Enabled = generationMode.SelectedIndex == 1;
        trainingTarget.Items.AddRange(["Solo resultado de las partidas", "Mixto: resultado y evaluación", "Evaluación de búsqueda"]);
        trainingTarget.SelectedIndex = 1;
        PopulateOpenings();
        tips.SetToolTip(dataset, "Tabla de posiciones usada por el entrenamiento directo. El ciclo completo la crea automáticamente con sus partidas nuevas.");
        tips.SetToolTip(hidden, "Tamaño de la capa oculta. 16 o 32 es una buena base; 64 necesita más partidas y reduce la velocidad del motor.");
        tips.SetToolTip(epochs, "Máximo de pasadas. Se conserva la mejor época de validación y se detiene si deja de mejorar.");
        tips.SetToolTip(selfplayGames, "Partidas nuevas que generarán los datos de aprendizaje. Se ejecutan por parejas con colores invertidos y se redondean para cubrir cada apertura.");
        tips.SetToolTip(evaluationGames, "Partidas independientes para decidir si la red nueva es mejor que la referencia. Se ejecutan por parejas y se redondean para cubrir cada apertura.");
        tips.SetToolTip(searchDepth, "Profundidad usada para cada jugada. Una profundidad mayor mejora las partidas, pero multiplica el tiempo necesario.");
        tips.SetToolTip(maxPlies, "Límite de medias jugadas por partida; 160 plies equivalen a 80 movimientos completos.");
        tips.SetToolTip(trainingTarget, "Mixto combina resultado y evaluación de búsqueda; usa la evaluación manual si no hay etiqueta de búsqueda.");
        tips.SetToolTip(openingSelection, "Marca las aperturas que se usarán en las partidas de aprendizaje y evaluación. Todas vienen marcadas al inicio.");
        tips.SetToolTip(customOpening, "Opcional: añade una línea propia. Ejemplo: Gambito de Rey | e4 e5 f4. Usa SAN o UCI separados por espacios.");
        tips.SetToolTip(stockfishEngine, "Ejecutable UCI nativo de Stockfish para medir la fuerza aproximada de ChessBot.");
        tips.SetToolTip(eloGames, "Partidas por nivel de Stockfish. Siempre se juegan en parejas con colores invertidos.");
        tips.SetToolTip(eloDepth, "Profundidad fija usada por ChessBot y Stockfish en la escalera Elo.");

        TabControl tabs = new() { Dock = DockStyle.Fill };
        tabs.TabPages.Add(BuildPlayTab());
        tabs.TabPages.Add(BuildTrainingTab());
        tabs.TabPages.Add(BuildToolsTab());
        Controls.Add(tabs);
        ApplyVisualStyle(tabs);
        board.SquareClicked += OnBoardClick;
        resignButton.Click += (_, _) => ResignGame();
        cancelButton.Click += (_, _) => CancelActiveTask();
        Shown += async (_, _) => await NewGameAsync();
        FormClosing += (_, _) => CancelActiveTask();
        FormClosed += (_, _) => tips.Dispose();
    }

    private void ApplyVisualStyle(TabControl tabs)
    {
        tabs.DrawMode = TabDrawMode.OwnerDrawFixed;
        tabs.SizeMode = TabSizeMode.Fixed;
        tabs.ItemSize = new Size(118, 32);
        tabs.Padding = new Point(14, 4);
        tabs.DrawItem += (_, eventArgs) =>
        {
            bool selected = eventArgs.Index == tabs.SelectedIndex;
            Color background = selected ? Accent : Paper;
            Color foreground = selected ? Color.White : Ink;
            using SolidBrush brush = new(background);
            eventArgs.Graphics.FillRectangle(brush, eventArgs.Bounds);
            TextRenderer.DrawText(eventArgs.Graphics, tabs.TabPages[eventArgs.Index].Text,
                                  Font, eventArgs.Bounds, foreground,
                                  TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
        };
        tabs.SelectedIndexChanged += (_, _) => tabs.Invalidate();
        StyleControls(tabs);
    }

    private void StyleControls(Control parent)
    {
        if (parent is not ChessBoard && parent != log)
        {
            parent.BackColor = parent is TextBoxBase or ComboBox or NumericUpDown or CheckedListBox
                ? Field : Paper;
            parent.ForeColor = Ink;
        }
        if (parent is Button button)
        {
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderSize = 0;
            button.BackColor = button == resignButton ? Color.FromArgb(143, 71, 57) : Accent;
            button.ForeColor = Color.White;
            button.Padding = new Padding(10, 4, 10, 4);
            button.Cursor = Cursors.Hand;
        }
        else if (parent is Label label)
        {
            label.ForeColor = Ink;
        }
        else if (parent is TabPage page)
        {
            page.BackColor = Paper;
        }
        foreach (Control child in parent.Controls)
            StyleControls(child);
    }

    private TabPage BuildPlayTab()
    {
        TabPage page = new("Jugar");
        TableLayoutPanel layout = new() { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1, Padding = new Padding(14) };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 67));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33));
        layout.Controls.Add(board, 0, 0);

        FlowLayoutPanel side = new()
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.TopDown,
            WrapContents = false,
            Padding = new Padding(18, 14, 14, 14),
            AutoScroll = true,
            BackColor = Color.FromArgb(255, 254, 250)
        };
        Label title = new() { Text = "Partida contra ChessBot", AutoSize = true, Font = new Font(Font, FontStyle.Bold), Margin = new Padding(3, 0, 3, 2) };
        Label subtitle = new() { Text = "Juega desde el tablero y sigue el estado de la partida.", AutoSize = true, MaximumSize = new Size(270, 0), ForeColor = Color.FromArgb(91, 102, 99), Margin = new Padding(3, 0, 3, 10) };
        Button newGame = new() { Text = "Nueva partida", AutoSize = true, Margin = new Padding(3, 10, 3, 3) };
        newGame.Click += async (_, _) => await NewGameAsync();
        side.Controls.Add(title);
        side.Controls.Add(subtitle);
        side.Controls.Add(Spacer());
        side.Controls.Add(new Label { Text = "Tu color", AutoSize = true });
        side.Controls.Add(playerColor);
        side.Controls.Add(new Label { Text = "Tiempo del motor (ms)", AutoSize = true, Margin = new Padding(3, 12, 3, 3) });
        side.Controls.Add(thinkTime);
        side.Controls.Add(newGame);
        side.Controls.Add(resignButton);
        side.Controls.Add(Spacer());
        side.Controls.Add(gameStatus);
        side.Controls.Add(new Label { Text = "Selecciona una pieza y después su casilla de destino. Las promociones se realizan a dama.", MaximumSize = new Size(270, 0), AutoSize = true, ForeColor = Color.DimGray, Margin = new Padding(3, 14, 3, 3) });
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
        outer.RowStyles.Add(new RowStyle(SizeType.Absolute, 100));
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
        for (int row = 0; row < 14; ++row)
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
        AddFieldRow(form, 9, "Aperturas", openingSelection);
        AddFieldRow(form, 10, "Apertura propia", customOpening);
        AddPathRow(form, 11, "Config. base", cycleConfig, "Examinar…", () => ChooseFile(cycleConfig, "JSON|*.json|Todos|*.*"));
        AddPathRow(form, 12, "Salida ciclo", cycleOutput, "Elegir…", () => ChooseFolder(cycleOutput));

        FlowLayoutPanel actions = new() { AutoSize = true, FlowDirection = FlowDirection.LeftToRight, Margin = new Padding(0, 12, 0, 0) };
        Button train = new() { Text = "Entrenar nueva red", AutoSize = true };
        train.Click += async (_, _) => await TrainAsync();
        Button cycle = new() { Text = "Ejecutar ciclo completo", AutoSize = true };
        cycle.Click += async (_, _) => await RunCycleAsync();
        actions.Controls.Add(train);
        actions.Controls.Add(cycle);
        actions.Controls.Add(cancelButton);
        form.Controls.Add(actions, 1, 13);
        outer.Controls.Add(explanation, 0, 0);
        outer.Controls.Add(form, 0, 1);
        outer.Controls.Add(log, 0, 2);
        page.Controls.Add(outer);
        return page;
    }

    private TabPage BuildToolsTab()
    {
        TabPage page = new("Herramientas");
        TableLayoutPanel layout = new() { Dock = DockStyle.Fill, RowCount = 4, Padding = new Padding(18) };
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
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
        Button trainingHistory = new() { Text = "Historial de entrenamientos", AutoSize = true };
        trainingHistory.Click += (_, _) => OpenTrainingHistory();
        Button project = new() { Text = "Abrir proyecto", AutoSize = true };
        project.Click += (_, _) => OpenFolder(root);
        buttons.Controls.AddRange([benchmark, build, results, trainingHistory, project]);
        FlowLayoutPanel eloControls = new()
        {
            AutoSize = true,
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = true,
            Margin = new Padding(0, 0, 0, 12)
        };
        eloControls.Controls.Add(new Label { Text = "Stockfish", AutoSize = true, Margin = new Padding(0, 7, 6, 0) });
        eloControls.Controls.Add(stockfishEngine);
        Button browseStockfish = new() { Text = "Examinar…", AutoSize = true };
        browseStockfish.Click += (_, _) => ChooseFile(stockfishEngine, "Ejecutable Stockfish|*.exe|Todos|*.*");
        eloControls.Controls.Add(browseStockfish);
        eloControls.Controls.Add(new Label { Text = "Partidas/nivel", AutoSize = true, Margin = new Padding(14, 7, 6, 0) });
        eloControls.Controls.Add(eloGames);
        eloControls.Controls.Add(new Label { Text = "Profundidad", AutoSize = true, Margin = new Padding(14, 7, 6, 0) });
        eloControls.Controls.Add(eloDepth);
        Button elo = new() { Text = "Medir Elo aproximado", AutoSize = true };
        elo.Click += async (_, _) => await RunEloLadderAsync();
        eloControls.Controls.Add(elo);
        layout.Controls.Add(state, 0, 0);
        layout.Controls.Add(buttons, 0, 1);
        layout.Controls.Add(eloControls, 0, 2);
        layout.Controls.Add(new RichTextBox
        {
            Dock = DockStyle.Fill,
            ReadOnly = true,
            Text =
            "BENCHMARK RÁPIDO\n" +
            "Mide velocidad y nodos por segundo del motor. Sirve para comprobar que la compilación funciona y comparar cambios.\n\n" +
            "COMPILAR / ACTUALIZAR\n" +
            "Configura y compila el motor C++ en modo Release. Úsalo después de cambiar el código del motor.\n\n" +
            "ABRIR RESULTADOS\n" +
            "Abre la carpeta build, donde se guardan datasets, redes, partidas, logs y ciclos de aprendizaje.\n\n" +
            "HISTORIAL DE ENTRENAMIENTOS\n" +
            "Abre el registro durable de todas las ejecuciones, incluidas las que quedaron interrumpidas por un apagado o crash.\n\n" +
            "ABRIR PROYECTO\n" +
            "Abre la carpeta raíz del proyecto para editar el código o revisar la configuración.\n\n" +
            "Ejecutable UCI actual:\n" + engine
        }, 0, 3);
        page.Controls.Add(layout);
        return page;
    }

    private async Task NewGameAsync()
    {
        moves.Clear();
        selectedSquare = null;
        gameFinished = false;
        resignButton.Enabled = false;
        SetGameStatus("Preparando partida…");
        currentFen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
        board.Position = currentFen;
        board.LastMove = null;
        board.SelectedSquare = null;
        board.CheckedSquare = null;
        board.Flipped = playerColor.SelectedIndex == 1;
        board.Invalidate();
        if (!File.Exists(engine))
        {
            gameStatus.Text = "Falta el motor. Usa Herramientas → Compilar/actualizar.";
            return;
        }
        resignButton.Enabled = true;
        await RefreshPositionAsync();
        if (playerColor.SelectedIndex == 1)
            await EngineMoveAsync();
    }

    private void ResignGame()
    {
        if (gameFinished || gameBusy || legalMoves.Count == 0)
            return;
        gameFinished = true;
        selectedSquare = null;
        legalMoves.Clear();
        board.SelectedSquare = null;
        board.TargetSquares.Clear();
        board.Invalidate();
        resignButton.Enabled = false;
        SetGameStatus("Te has rendido · gana ChessBot", finished: true);
    }

    private async void OnBoardClick(object? sender, string square)
    {
        if (gameFinished || gameBusy || SideToMoveIsWhite() != PlayerIsWhite())
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
        List<string> candidates = legalMoves
            .Where(candidate => candidate.StartsWith(prefix, StringComparison.Ordinal))
            .ToList();
        string? move = candidates.Count == 1 ? candidates[0] : null;
        if (candidates.Count > 1 && ChoosePromotion(candidates) is char promotion)
            move = candidates.FirstOrDefault(candidate => candidate.EndsWith(promotion));
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

    private char? ChoosePromotion(IReadOnlyCollection<string> candidates)
    {
        using Form dialog = new()
        {
            Text = "Elige la promoción",
            StartPosition = FormStartPosition.CenterParent,
            FormBorderStyle = FormBorderStyle.FixedDialog,
            MinimizeBox = false,
            MaximizeBox = false,
            ShowInTaskbar = false,
            ClientSize = new Size(360, 92),
            BackColor = Paper,
            ForeColor = Ink
        };
        FlowLayoutPanel buttons = new()
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = false,
            Padding = new Padding(12)
        };
        foreach ((char code, string name) in new[] { ('q', "Dama"), ('r', "Torre"), ('b', "Alfil"), ('n', "Caballo") })
        {
            if (!candidates.Any(move => move.EndsWith(code)))
                continue;
            Button button = new() { Text = name, Tag = code, AutoSize = true, DialogResult = DialogResult.OK };
            button.Click += (_, _) => dialog.Tag = code;
            buttons.Controls.Add(button);
        }
        dialog.Controls.Add(buttons);
        return dialog.ShowDialog(this) == DialogResult.OK && dialog.Tag is char choice ? choice : null;
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
            bool inCheck = rootElement.TryGetProperty("in_check", out JsonElement checkElement) &&
                           checkElement.GetBoolean();
            board.CheckedSquare = inCheck ? FindKingSquare(currentFen) : null;
            board.Position = currentFen;
            board.LastMove = moves.LastOrDefault();
            board.Invalidate();
            if (status == "ongoing")
            {
                gameFinished = false;
                resignButton.Enabled = true;
                string turn = SideToMoveIsWhite() ? "Turno de blancas" : "Turno de negras";
                SetGameStatus(inCheck ? $"Jaque · {turn}" : turn, warning: inCheck);
            }
            else
            {
                gameFinished = true;
                resignButton.Enabled = false;
                bool checkmate = status == "checkmate";
                string result = checkmate
                    ? $"JAQUE MATE · ganan {(SideToMoveIsWhite() ? "negras" : "blancas")}"
                    : TranslateStatus(status);
                SetGameStatus(result, finished: true);
            }
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
        if (gameFinished)
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
             "--target", TargetValue(), "--teacher-weight", "1.0", "--learning-rate", "0.0003",
             "--seed", "7"], "Entrenamiento NNUE");
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
        bool completed = await RunTaskAsync(python,
            ["tools/learning_cycle.py", "--config", generatedConfig, "--engine", engine, "--output-dir", cycleOutput.Text],
            "Ciclo completo", false);
        string decisionPath = Path.Combine(cycleOutput.Text, "evaluation", "decision.json");
        if (completed && File.Exists(decisionPath))
        {
            JsonObject decision = JsonNode.Parse(File.ReadAllText(decisionPath))!.AsObject();
            bool accepted = decision["decision"]?.GetValue<string>() == "accept";
            bool promoted = decision["artifacts"]?["promoted_to"] is not null;
            string message = accepted
                ? (promoted ? "Red ACEPTADA y guardada como referencia activa." : "Red ACEPTADA; no se configuró promoción.")
                : "Red RECHAZADA. La referencia activa se conserva.\nLa candidata y sus informes siguen guardados.";
            AppendLog(message + "\nInforme: " + decisionPath + "\n");
            MessageBox.Show(message + "\n\nInforme: " + decisionPath, "Resultado del ciclo",
                            MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
        else
        {
            MessageBox.Show("El ciclo no terminó correctamente. Revisa el registro.", "Resultado del ciclo",
                            MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
    }

    private async Task RunEloLadderAsync()
    {
        if (!File.Exists(stockfishEngine.Text))
        {
            MessageBox.Show("Selecciona un ejecutable stockfish.exe.", "Medir Elo",
                            MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        string output = NewOutput("elo-ladder");
        await RunTaskAsync(python,
            ["tools/elo_ladder.py", "--engine", engine, "--stockfish", stockfishEngine.Text,
             "--games-per-level", eloGames.Value.ToString(), "--depth", eloDepth.Value.ToString(),
             "--output-dir", output], "Escalera Elo");
    }

    private void PopulateOpenings()
    {
        string path = Path.Combine(root, "data", "openings", "core.json");
        if (!File.Exists(path))
            return;
        try
        {
            using JsonDocument document = JsonDocument.Parse(File.ReadAllText(path));
            foreach (JsonElement item in document.RootElement.GetProperty("openings").EnumerateArray())
            {
                string id = item.GetProperty("id").GetString() ?? string.Empty;
                string name = item.GetProperty("name").GetString() ?? id;
                string eco = item.TryGetProperty("eco", out JsonElement ecoElement) &&
                             ecoElement.ValueKind != JsonValueKind.Null ? $" ({ecoElement.GetString()})" : string.Empty;
                if (!string.IsNullOrWhiteSpace(id))
                    openingSelection.Items.Add(new OpeningChoice(id, name + eco), true);
            }
        }
        catch (Exception exception)
        {
            AppendLog($"No se pudieron cargar las aperturas: {exception.Message}\n");
        }
    }

    private string CreateCycleConfig()
    {
        JsonObject config = JsonNode.Parse(File.ReadAllText(cycleConfig.Text))?.AsObject() ??
                            throw new InvalidDataException("El JSON base está vacío");
        string stamp = DateTime.Now.ToString("yyyyMMdd-HHmmss");
        config["id"] = "launcher-cycle-" + stamp;
        config["candidate_version"] = string.IsNullOrWhiteSpace(version.Text) ? "launcher-nnue-" + stamp : version.Text.Trim();
        config["source_pgns"] = new JsonArray();
        string activeNetwork = Path.Combine(root, "data", "networks", "nnue-active.nnue");
        if (File.Exists(activeNetwork))
        {
            config["reference"] = "data/networks/nnue-active.nnue";
            config["reference_kind"] = "nnue";
        }

        JsonObject budgets = ObjectAt(config, "budgets");
        budgets["max_seconds"] = (int)maxMinutes.Value * 60;
        budgets["max_storage_mb"] = 512;

        List<OpeningChoice> selectedOpenings = SelectedOpenings();
        bool hasCustomOpening = !string.IsNullOrWhiteSpace(customOpening.Text);
        if (!hasCustomOpening && selectedOpenings.Count == 0)
            throw new InvalidDataException("Selecciona al menos una apertura o escribe una apertura propia");
        string? customOpeningsPath = hasCustomOpening
            ? CreateCustomOpeningSource(stamp, selectedOpenings)
            : null;
        int openingCount = selectedOpenings.Count + (hasCustomOpening ? 1 : 0);
        int adjustedSelfplay = PairedCount(selfplayGames.Value, openingCount);
        int adjustedEvaluation = PairedCount(evaluationGames.Value, openingCount);
        budgets["selfplay_games"] = adjustedSelfplay;
        budgets["evaluation_games"] = adjustedEvaluation;
        if (adjustedSelfplay != (int)selfplayGames.Value || adjustedEvaluation != (int)evaluationGames.Value)
            AppendLog($"Emparejado: {openingCount} aperturas × 2 colores; partidas ajustadas a {adjustedSelfplay} / {adjustedEvaluation}.\n");
        if (customOpeningsPath is not null)
            config["openings"] = customOpeningsPath;

        JsonObject selfplay = ObjectAt(config, "selfplay");
        selfplay["enabled"] = true;
        selfplay["depth"] = (int)searchDepth.Value;
        selfplay["max_plies"] = (int)maxPlies.Value;
        if (customOpeningsPath is null)
            selfplay["opening_ids"] = OpeningIds(selectedOpenings);
        else
            selfplay.Remove("opening_ids");
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
        if (customOpeningsPath is null)
            evaluation["opening_ids"] = OpeningIds(selectedOpenings);
        else
            evaluation.Remove("opening_ids");
        evaluation["minimum_lower_score"] = 0.5;
        // Repeated games from the same opening do not create independent samples.
        // Count distinct generated prefixes, not merely the number of game pairs.
        evaluation["minimum_independent_samples"] = 16;

        string configDirectory = Path.Combine(root, "build", "launcher-configs");
        Directory.CreateDirectory(configDirectory);
        string path = Path.Combine(configDirectory, "cycle-" + stamp + ".json");
        File.WriteAllText(path, config.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + Environment.NewLine);
        return path;
    }

    private List<OpeningChoice> SelectedOpenings() =>
        openingSelection.CheckedItems.OfType<OpeningChoice>().ToList();

    private static JsonArray OpeningIds(IEnumerable<OpeningChoice> openings)
    {
        JsonArray result = [];
        foreach (OpeningChoice opening in openings)
            result.Add(opening.Id);
        return result;
    }

    private string CreateCustomOpeningSource(string stamp, IReadOnlyCollection<OpeningChoice> selected)
    {
        string corePath = Path.Combine(root, "data", "openings", "core.json");
        JsonObject core = JsonNode.Parse(File.ReadAllText(corePath))?.AsObject() ??
                          throw new InvalidDataException("El catálogo de aperturas está vacío");
        JsonArray openings = [];
        HashSet<string> selectedIds = selected.Select(opening => opening.Id).ToHashSet(StringComparer.Ordinal);
        if (core["openings"] is JsonArray coreOpenings)
        {
            foreach (JsonNode? node in coreOpenings)
            {
                if (node is JsonObject opening &&
                    selectedIds.Contains(opening["id"]?.GetValue<string>() ?? string.Empty))
                    openings.Add(opening.DeepClone());
            }
        }

        string raw = customOpening.Text.Trim();
        string name = "Apertura personalizada";
        string movesText = raw;
        int separator = raw.IndexOf('|');
        if (separator >= 0)
        {
            string requestedName = raw[..separator].Trim();
            if (!string.IsNullOrWhiteSpace(requestedName))
                name = requestedName;
            movesText = raw[(separator + 1)..].Trim();
        }
        string[] moves = movesText.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
        if (moves.Length == 0)
            throw new InvalidDataException("La apertura propia necesita movimientos, por ejemplo: Gambito de Rey | e4 e5 f4");
        openings.Add(new JsonObject
        {
            ["id"] = "custom_1",
            ["name"] = name,
            ["eco"] = null,
            ["start_fen"] = "startpos",
            ["moves"] = new JsonArray(moves.Select(move => (JsonNode?)move).ToArray())
        });

        JsonObject payload = new()
        {
            ["schema_version"] = 1,
            ["version"] = "launcher-custom-" + stamp,
            ["openings"] = openings
        };
        string directory = Path.Combine(root, "build", "launcher-configs");
        Directory.CreateDirectory(directory);
        string path = Path.Combine(directory, "openings-" + stamp + ".json");
        File.WriteAllText(path, payload.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + Environment.NewLine);
        return path;
    }

    private string TargetValue() => trainingTarget.SelectedIndex switch
    {
        1 => "mixed",
        2 => "search",
        _ => "result"
    };

    private static int PairedCount(decimal value, int openingCount)
    {
        int count = Math.Max(2, (int)value);
        int pairSize = Math.Max(1, openingCount) * 2;
        int remainder = count % pairSize;
        return remainder == 0 ? count : count + pairSize - remainder;
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

    private void OpenTrainingHistory()
    {
        string path = Path.Combine(root, "build", "training-history.jsonl");
        if (!File.Exists(path))
        {
            MessageBox.Show("Todavía no hay ejecuciones registradas.", "Historial de entrenamientos",
                            MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        Process.Start(new ProcessStartInfo { FileName = path, UseShellExecute = true });
    }

    private void SetGameStatus(string text, bool warning = false, bool finished = false)
    {
        gameStatus.Text = text;
        gameStatus.BackColor = finished ? Color.FromArgb(247, 220, 214) : warning ? Color.FromArgb(255, 239, 194) : AccentLight;
        gameStatus.ForeColor = finished ? Color.FromArgb(130, 46, 36) : warning ? Color.FromArgb(111, 76, 20) : Ink;
    }

    private static string? FindKingSquare(string fen)
    {
        string[] fields = fen.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        if (fields.Length < 2)
            return null;
        char king = fields[1] == "w" ? 'K' : 'k';
        string[] ranks = fields[0].Split('/');
        for (int rankIndex = 0; rankIndex < ranks.Length; ++rankIndex)
        {
            int file = 0;
            foreach (char piece in ranks[rankIndex])
            {
                if (char.IsDigit(piece))
                    file += piece - '0';
                else
                {
                    if (piece == king)
                        return $"{(char)('a' + file)}{8 - rankIndex}";
                    ++file;
                }
            }
        }
        return null;
    }

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
        "threefold" or "threefold_repetition" => "Tablas por repetición",
        "fifty_move" => "Tablas por cincuenta movimientos",
        "insufficient_material" => "Tablas por material insuficiente",
        _ => "Partida terminada: " + status
    };

    private static Control Spacer() => new Panel { Height = 8, Width = 8 };

    private static void AddPathRow(TableLayoutPanel panel, int row, string label, TextBox box, string buttonText, Action action)
    {
        panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        panel.Controls.Add(new Label { Text = label, AutoSize = true, Anchor = AnchorStyles.Left, Margin = new Padding(0, 3, 10, 3) }, 0, row);
        panel.Controls.Add(box, 1, row);
        Button button = new() { Text = buttonText, AutoSize = true };
        button.Click += (_, _) => action();
        panel.Controls.Add(button, 2, row);
    }

    private static void AddFieldRow(TableLayoutPanel panel, int row, string label, Control control)
    {
        panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        panel.Controls.Add(new Label { Text = label, AutoSize = true, Anchor = AnchorStyles.Left, Margin = new Padding(0, 3, 10, 3) }, 0, row);
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

internal sealed record OpeningChoice(string Id, string DisplayName)
{
    public override string ToString() => DisplayName;
}

internal sealed class ChessBoard : Control
{
    private static readonly Dictionary<char, string> Symbols = new()
    {
        // Usamos los glifos BLACK CHESS para ambos bandos: a diferencia de
        // WHITE CHESS, estos tienen una silueta sólida que sí admite relleno.
        ['K'] = "♚",
        ['Q'] = "♛",
        ['R'] = "♜",
        ['B'] = "♝",
        ['N'] = "♞",
        ['P'] = "♟",
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
    public string? CheckedSquare { get; set; }
    [Browsable(false), DesignerSerializationVisibility(DesignerSerializationVisibility.Hidden)]
    public string? LastMove { get; set; }
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
        e.Graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
        e.Graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;
        int size = Math.Min(ClientSize.Width, ClientSize.Height) - 16;
        int cell = size / 8;
        int boardSize = cell * 8;
        int left = (ClientSize.Width - boardSize) / 2;
        int top = (ClientSize.Height - boardSize) / 2;
        using SolidBrush frameBrush = new(Color.FromArgb(39, 49, 48));
        e.Graphics.FillRectangle(frameBrush, new Rectangle(left - 5, top - 5, boardSize + 10, boardSize + 10));
        using Font pieceFont = new("Segoe UI Symbol", cell * 0.68f, FontStyle.Regular, GraphicsUnit.Pixel);
        using Font coordinateFont = new("Segoe UI", Math.Max(8, cell * 0.13f), FontStyle.Bold, GraphicsUnit.Pixel);
        using StringFormat centered = new() { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
        (string? from, string? to) = LastMove is { Length: >= 4 } move
            ? (move[..2], move.Substring(2, 2))
            : (null, null);
        for (int displayRank = 0; displayRank < 8; ++displayRank)
        {
            for (int displayFile = 0; displayFile < 8; ++displayFile)
            {
                int file = Flipped ? 7 - displayFile : displayFile;
                int rank = Flipped ? displayRank : 7 - displayRank;
                string square = $"{(char)('a' + file)}{rank + 1}";
                Rectangle rectangle = new(left + displayFile * cell, top + displayRank * cell, cell, cell);
                bool light = (file + rank) % 2 != 0;
                Color color = light ? Color.FromArgb(242, 226, 190) : Color.FromArgb(126, 156, 91);
                bool isLastMove = square == from || square == to;
                if (isLastMove)
                    color = light ? Color.FromArgb(246, 211, 102) : Color.FromArgb(210, 169, 57);
                if (square == CheckedSquare)
                    color = Color.FromArgb(219, 106, 91);
                else if (square == SelectedSquare)
                    color = Color.FromArgb(255, 241, 122);
                using SolidBrush background = new(color);
                e.Graphics.FillRectangle(background, rectangle);
                if (TargetSquares.Contains(square))
                {
                    bool occupied = pieces.ContainsKey(square);
                    Color marker = occupied ? Color.FromArgb(85, 95, 73) : Color.FromArgb(72, 118, 77);
                    using SolidBrush markerBrush = new(marker);
                    if (occupied)
                    {
                        using Pen capturePen = new(Color.FromArgb(170, marker), Math.Max(2, cell * 0.045f));
                        e.Graphics.DrawEllipse(capturePen, rectangle.X + cell * 0.14f, rectangle.Y + cell * 0.14f,
                                               cell * 0.72f, cell * 0.72f);
                    }
                    else
                    {
                        float markerSize = Math.Max(8, cell * 0.18f);
                        e.Graphics.FillEllipse(markerBrush,
                                               rectangle.X + (cell - markerSize) / 2,
                                               rectangle.Y + (cell - markerSize) / 2,
                                               markerSize, markerSize);
                    }
                }
                if (pieces.TryGetValue(square, out char piece))
                {
                    bool whitePiece = char.IsUpper(piece);
                    Color outlineColor = whitePiece ? Color.FromArgb(38, 48, 46) : Color.FromArgb(250, 248, 242);
                    Color pieceColor = whitePiece ? Color.FromArgb(255, 255, 250) : Color.FromArgb(25, 29, 28);
                    using SolidBrush shadow = new(Color.FromArgb(30, 0, 0, 0));
                    e.Graphics.DrawString(Symbols[piece], pieceFont, shadow,
                                          new Rectangle(rectangle.X + 1, rectangle.Y + 1, rectangle.Width, rectangle.Height), centered);
                    using SolidBrush outline = new(outlineColor);
                    int outlineWidth = Math.Max(1, (int)Math.Round(cell * 0.012f));
                    foreach ((int offsetX, int offsetY) in new[]
                             { (-outlineWidth, 0), (outlineWidth, 0), (0, -outlineWidth), (0, outlineWidth) })
                    {
                        Rectangle outlineRect = new(rectangle.X + offsetX, rectangle.Y + offsetY,
                                                    rectangle.Width, rectangle.Height);
                        e.Graphics.DrawString(Symbols[piece], pieceFont, outline, outlineRect, centered);
                    }
                    using SolidBrush foreground = new(pieceColor);
                    e.Graphics.DrawString(Symbols[piece], pieceFont, foreground, rectangle, centered);
                }
                if (displayFile == 0)
                {
                    using SolidBrush brush = new(ContrastForCoordinate(color));
                    e.Graphics.DrawString((rank + 1).ToString(), coordinateFont, brush, rectangle.X + 3, rectangle.Y + 2);
                }
                if (displayRank == 7)
                {
                    using SolidBrush brush = new(ContrastForCoordinate(color));
                    e.Graphics.DrawString(((char)('a' + file)).ToString(), coordinateFont, brush, rectangle.Right - coordinateFont.Size - 3, rectangle.Bottom - coordinateFont.Height - 1);
                }
                if (isLastMove && square != CheckedSquare)
                {
                    using Pen lastMovePen = new(Color.FromArgb(185, 125, 30), Math.Max(1, cell * 0.025f));
                    e.Graphics.DrawRectangle(lastMovePen, rectangle.X, rectangle.Y, rectangle.Width - 1, rectangle.Height - 1);
                }
                if (square == SelectedSquare)
                {
                    using Pen selectedPen = new(Color.FromArgb(42, 79, 70), Math.Max(2, cell * 0.04f));
                    e.Graphics.DrawRectangle(selectedPen, rectangle.X + 2, rectangle.Y + 2, rectangle.Width - 5, rectangle.Height - 5);
                }
            }
        }
    }

    private static Color ContrastForCoordinate(Color square) =>
        square.GetBrightness() > 0.55f ? Color.FromArgb(102, 72, 37) : Color.FromArgb(247, 239, 207);

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
