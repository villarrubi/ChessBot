using System.Diagnostics;
using System.Net.Http;
using System.Text;
using System.Text.Json;

namespace ChessBotLauncher;

internal sealed class AnalysisTab : TabPage
{
    private readonly string root;
    private readonly string engine;
    private readonly string python;
    private readonly Func<string[]> currentGame;
    private readonly ChessBoard board = new() { Dock = DockStyle.Fill, MinimumSize = Size.Empty,
        Position = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1" };
    private readonly ComboBox source = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 90 };
    private readonly TextBox input = new() { Multiline = true, ScrollBars = ScrollBars.Vertical, Dock = DockStyle.Fill,
        PlaceholderText = "Pega aquí una partida PGN o una posición FEN." };
    private readonly NumericUpDown depth = new() { Minimum = 1, Maximum = 126, Value = 4, Width = 55 };
    private readonly NumericUpDown multipv = new() { Minimum = 1, Maximum = 256, Value = 3, Width = 55 };
    private readonly NumericUpDown threads = new() { Name = "analysisThreads", Minimum = 1, Maximum = 256,
        Value = Math.Clamp(Environment.ProcessorCount / 2, 1, 8), Width = 55 };
    private readonly ComboBox games = new() { DropDownStyle = ComboBoxStyle.DropDownList, Dock = DockStyle.Fill };
    private readonly ComboBox provider = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 135 };
    private readonly ComboBox model = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 150 };
    private readonly DataGridView grid = new() { Dock = DockStyle.Fill, ReadOnly = true, AllowUserToAddRows = false,
        AllowUserToDeleteRows = false, AllowUserToResizeRows = false, RowHeadersVisible = false,
        MultiSelect = false, SelectionMode = DataGridViewSelectionMode.FullRowSelect,
        AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill, BackgroundColor = Color.White,
        BorderStyle = BorderStyle.None };
    private readonly RichTextBox evidence = new() { Dock = DockStyle.Fill, ReadOnly = true, BorderStyle = BorderStyle.None };
    private readonly RichTextBox answer = new() { Dock = DockStyle.Fill, ReadOnly = true, BorderStyle = BorderStyle.None,
        Text = "Selecciona una jugada y pulsa Explicar con IA. El motor calcula las variantes; la IA las comenta." };
    private readonly TextBox question = new() { Dock = DockStyle.Fill, PlaceholderText = "¿Por qué prefiere esta jugada?" };
    private readonly TextBox alternative = new() { Width = 95, PlaceholderText = "Nf3 / g1f3" };
    private readonly TextBox fen = new() { Dock = DockStyle.Fill, ReadOnly = true };
    private readonly CheckBox after = new() { Text = "Después de la jugada", AutoSize = true, Checked = true };
    private readonly Button chartToggle = new() { Text = "Gráfico de evaluación ▾", AutoSize = true };
    private readonly EvaluationChart evaluationChart = new() { Dock = DockStyle.Fill, Visible = false };
    private readonly Label status = new() { Text = "Importa un PGN, pega una FEN o carga tu partida actual.", AutoSize = true, Dock = DockStyle.Fill };
    private readonly Button cancel = new() { Text = "Cancelar", AutoSize = true, Enabled = false };
    private readonly List<Control> lockedControls = [];
    private readonly TabControl explanations = new() { Dock = DockStyle.Fill };
    private JsonElement payload;
    private JsonElement[] records = [];
    private string? outputDirectory;
    private CancellationTokenSource? cancellation;
    private bool loading;
    private TableLayoutPanel? rightLayout;
    private bool chartExpanded;

    public AnalysisTab(string projectRoot, string enginePath, string pythonPath, Func<string[]> gameMoves) : base("Análisis")
    {
        root = projectRoot;
        engine = enginePath;
        python = pythonPath;
        currentGame = gameMoves;
        fen.Text = board.Position;
        source.Items.AddRange(["PGN", "FEN"]);
        source.SelectedIndex = 0;
        provider.Items.AddRange(["IA local (Ollama)", "Solo motor"]);
        provider.SelectedIndex = 0;
        model.Items.Add("Automático");
        model.SelectedIndex = 0;

        TableLayoutPanel layout = new() { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 4, Padding = new Padding(12) };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 65));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        FlowLayoutPanel toolbar = Flow();
        toolbar.Controls.Add(source);
        toolbar.Controls.Add(ActionButton("Importar PGN", ImportPgnAsync));
        toolbar.Controls.Add(ActionButton("Partida actual", () => AnalyzeAsync("game", currentGame())));
        toolbar.Controls.Add(Caption("Prof."));
        toolbar.Controls.Add(depth);
        toolbar.Controls.Add(Caption("Variantes"));
        toolbar.Controls.Add(multipv);
        toolbar.Controls.Add(Caption("Hilos"));
        toolbar.Controls.Add(threads);
        toolbar.Controls.Add(ActionButton("Analizar", () => AnalyzeAsync(source.SelectedIndex == 0 ? "pgn" : "fen")));
        toolbar.Controls.Add(cancel);
        toolbar.Controls.Add(ActionButton("Resultados", ExportAsync));
        layout.Controls.Add(toolbar, 0, 0);
        layout.Controls.Add(input, 0, 1);

        TableLayoutPanel content = new() { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1 };
        content.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 43));
        content.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 57));
        TableLayoutPanel left = new() { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 3 };
        left.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        left.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        left.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        left.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        left.Controls.Add(board, 0, 0);
        FlowLayoutPanel navigation = Flow();
        navigation.Controls.Add(ActionButton("◀", () => NavigateAsync(-1)));
        navigation.Controls.Add(ActionButton("▶", () => NavigateAsync(1)));
        navigation.Controls.Add(after);
        navigation.Controls.Add(ActionButton("Girar", () => { board.Flipped = !board.Flipped; board.Invalidate(); return Task.CompletedTask; }));
        left.Controls.Add(navigation, 0, 1);
        left.Controls.Add(fen, 0, 2);
        content.Controls.Add(left, 0, 0);

        TableLayoutPanel right = new() { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 8, Padding = new Padding(8, 0, 0, 0) };
        right.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        right.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        right.RowStyles.Add(new RowStyle(SizeType.Absolute, 132));
        right.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        right.RowStyles.Add(new RowStyle(SizeType.Absolute, 0));
        right.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        right.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        right.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        right.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        right.Controls.Add(games, 0, 0);
        foreach (string name in new[] { "Jugada", "Valoración", "Eval.", "Pérdida", "Mejor" })
        {
            int index = grid.Columns.Add(name, name);
            grid.Columns[index].SortMode = DataGridViewColumnSortMode.NotSortable;
        }
        right.Controls.Add(grid, 0, 1);
        right.Controls.Add(chartToggle, 0, 2);
        right.Controls.Add(evaluationChart, 0, 3);
        TabPage factsPage = new("Cálculos del motor");
        factsPage.Controls.Add(evidence);
        TabPage aiPage = new("Explicación IA");
        aiPage.Controls.Add(answer);
        explanations.TabPages.AddRange([factsPage, aiPage]);
        right.Controls.Add(explanations, 0, 4);
        FlowLayoutPanel aiSettings = Flow();
        aiSettings.Controls.Add(provider);
        aiSettings.Controls.Add(model);
        aiSettings.Controls.Add(ActionButton("Detectar IA", DetectModelsAsync));
        right.Controls.Add(aiSettings, 0, 5);
        right.Controls.Add(question, 0, 6);
        FlowLayoutPanel askRow = Flow();
        askRow.Controls.Add(Caption("Alternativa"));
        askRow.Controls.Add(alternative);
        askRow.Controls.Add(ActionButton("Explicar / preguntar", ExplainAsync));
        right.Controls.Add(askRow, 0, 7);
        content.Controls.Add(right, 1, 0);
        rightLayout = right;
        lockedControls.Add(chartToggle);
        chartToggle.Click += (_, _) => SetChartExpanded(!chartExpanded);
        layout.Controls.Add(content, 0, 2);
        layout.Controls.Add(status, 0, 3);
        Controls.Add(layout);
        lockedControls.AddRange([input, source, depth, multipv, games, grid, provider, model, question, alternative, after]);
        lockedControls.Add(threads);
        cancel.Click += (_, _) => cancellation?.Cancel();
        games.SelectedIndexChanged += (_, _) => LoadGame();
        grid.CurrentCellChanged += (_, _) => SelectMove();
        after.CheckedChanged += (_, _) => UpdateBoard();
        Disposed += (_, _) => cancellation?.Cancel();
    }

    private static FlowLayoutPanel Flow() => new() { Dock = DockStyle.Fill, AutoSize = true, WrapContents = true, Margin = new Padding(0) };
    private static Label Caption(string text) => new() { Text = text, AutoSize = true, Margin = new Padding(3, 8, 3, 0) };

    private Button ActionButton(string text, Func<Task> action)
    {
        Button button = new() { Text = text, AutoSize = true };
        lockedControls.Add(button);
        button.Click += async (_, _) =>
        {
            try { await action(); }
            catch (Exception error) { if (!IsDisposed) status.Text = error.Message; }
        };
        return button;
    }

    private async Task ImportPgnAsync()
    {
        using OpenFileDialog dialog = new() { Filter = "Partidas PGN|*.pgn|Todos los archivos|*.*", InitialDirectory = root };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        input.Text = await File.ReadAllTextAsync(dialog.FileName);
        source.SelectedIndex = 0;
        await AnalyzeAsync("pgn");
    }

    private async Task AnalyzeAsync(string kind, string[]? moves = null)
    {
        if (!File.Exists(engine) || !File.Exists(python))
            throw new InvalidOperationException("Falta el motor o el entorno Python. Consulta la guía de instalación.");
        string directory = Path.Combine(root, "data", "analysis", DateTime.Now.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N")[..6]);
        string request = Path.Combine(directory, "request.json");
        string requestJson = JsonSerializer.Serialize(new { kind, text = input.Text, moves,
            depth = (int)depth.Value, multipv = (int)multipv.Value, threads = (int)threads.Value });
        await RunTaskAsync("Calculando variantes…", async token =>
        {
            Directory.CreateDirectory(directory);
            await File.WriteAllTextAsync(request, requestJson, token);
            await RunPythonAsync(["tools/analysis_session.py", "--request", request, "--engine", engine, "--output-dir", directory], token);
            using JsonDocument document = JsonDocument.Parse(await File.ReadAllTextAsync(Path.Combine(directory, "analysis.json"), token));
            payload = document.RootElement.Clone();
            outputDirectory = directory;
            games.Items.Clear();
            int index = 0;
            foreach (JsonElement game in payload.GetProperty("games").EnumerateArray())
            {
                JsonElement headers = game.GetProperty("headers");
                games.Items.Add($"{++index}. {headers.GetProperty("White").GetString()} — {headers.GetProperty("Black").GetString()}");
            }
            games.SelectedIndex = 0;
            status.Text = "Análisis listo · puntuaciones relativas al jugador de cada fila · resultados guardados.";
        });
    }

    private void LoadGame()
    {
        if (games.SelectedIndex < 0) return;
        JsonElement game = payload.GetProperty("games")[games.SelectedIndex];
        records = game.GetProperty("moves").EnumerateArray().ToArray();
        evaluationChart.SetRecords(records);
        loading = true;
        grid.Rows.Clear();
        foreach (JsonElement record in records)
        {
            string prefix = record.GetProperty("move_number").GetInt32() + (record.GetProperty("color").GetString() == "white" ? ". " : "… ");
            JsonElement loss = record.GetProperty("centipawn_loss");
            grid.Rows.Add(prefix + record.GetProperty("move_san").GetString(), Label(record.GetProperty("classification").GetString()),
                Score(record.GetProperty("played").GetProperty("score")),
                loss.ValueKind == JsonValueKind.Null ? "Mate" : (loss.GetInt32() / 100.0).ToString("0.00"),
                record.GetProperty("best").GetProperty("san").GetString() ?? "—");
        }
        loading = false;
        if (grid.Rows.Count > 0)
        {
            grid.CurrentCell = grid.Rows[0].Cells[0];
            SelectMove();
        }
        else
        {
            board.Position = game.GetProperty("fen").GetString()!;
            board.LastMove = null;
            fen.Text = board.Position;
            evidence.Text = "No hay jugadas que analizar. La posición es terminal o el PGN no contiene movimientos.";
            answer.Clear();
            evaluationChart.SetRecords([]);
        }
    }

    private int SelectedIndex => grid.CurrentRow?.Index ?? -1;
    private void SelectMove()
    {
        if (loading || SelectedIndex < 0 || SelectedIndex >= records.Length) return;
        JsonElement record = records[SelectedIndex];
        StringBuilder text = new(record.GetProperty("explanation").GetString());
        text.AppendLine("\n\nAlternativas calculadas:");
        foreach (JsonElement candidate in record.GetProperty("candidates").EnumerateArray())
        {
            string line = string.Join(" ", candidate.GetProperty("pv_san").EnumerateArray().Select(value => value.GetString()));
            text.AppendLine($"{candidate.GetProperty("san").GetString()}: {Score(candidate.GetProperty("score"))} · profundidad {candidate.GetProperty("depth")}\n{line}\n");
        }
        foreach (string key in new[] { "static_before", "static_after", "static_best_after" })
        {
            if (!record.TryGetProperty(key, out JsonElement value)) continue;
            if (value.ValueKind == JsonValueKind.Object)
            {
                text.AppendLine(key switch
                {
                    "static_before" => "Evaluación estática antes (cp):",
                    "static_after" => "Evaluación estática tras la jugada (cp):",
                    _ => "Evaluación estática tras la mejor alternativa (cp):"
                });
                foreach (JsonProperty component in value.EnumerateObject().Where(p => p.Value.ValueKind == JsonValueKind.Number))
                    if (ComponentLabel(component.Name) is string label) text.AppendLine($"  {label}: {component.Value}");
            }
        }
        evidence.Text = text.ToString();
        answer.Text = "Pulsa Explicar / preguntar para comentar esta posición con la IA local.";
        alternative.Clear();
        evaluationChart.SelectedIndex = SelectedIndex;
        UpdateBoard();
    }

    private void SetChartExpanded(bool expanded)
    {
        chartExpanded = expanded;
        evaluationChart.Visible = expanded;
        chartToggle.Text = expanded ? "Gráfico de evaluación ▴" : "Gráfico de evaluación ▾";
        if (rightLayout is not null)
        {
            rightLayout.RowStyles[3] = new RowStyle(SizeType.Absolute, expanded ? 180 : 0);
            rightLayout.PerformLayout();
        }
    }

    private void UpdateBoard()
    {
        if (SelectedIndex < 0 || SelectedIndex >= records.Length) return;
        JsonElement record = records[SelectedIndex];
        board.Position = record.GetProperty(after.Checked ? "fen_after" : "fen_before").GetString()!;
        board.LastMove = after.Checked ? record.GetProperty("move_uci").GetString() : null;
        board.Invalidate();
        fen.Text = board.Position;
    }

    private Task NavigateAsync(int direction)
    {
        if (grid.Rows.Count > 0)
            grid.CurrentCell = grid.Rows[Math.Clamp(SelectedIndex + direction, 0, grid.Rows.Count - 1)].Cells[0];
        return Task.CompletedTask;
    }

    private async Task ExplainAsync()
    {
        if (outputDirectory is null || SelectedIndex < 0) throw new InvalidOperationException("Analiza y selecciona una jugada primero.");
        string result = Path.Combine(outputDirectory, "explanation.json");
        List<string> arguments = ["tools/explain_analysis.py", "--analysis", Path.Combine(outputDirectory, "analysis.json"),
            "--game", (games.SelectedIndex + 1).ToString(), "--ply", records[SelectedIndex].GetProperty("ply").ToString(),
            "--engine", engine, "--question", question.Text, "--move", alternative.Text.Trim(),
            "--provider", provider.SelectedIndex == 0 ? "auto" : "none", "--json-output", result,
            "--context-output", Path.Combine(outputDirectory, "explanation-context.json")];
        if (model.SelectedIndex > 0) arguments.AddRange(["--model", model.Text]);
        await RunTaskAsync("Preparando explicación local…", async token =>
        {
            await RunPythonAsync(arguments, token);
            using JsonDocument document = JsonDocument.Parse(await File.ReadAllTextAsync(result, token));
            JsonElement response = document.RootElement;
            answer.Text = response.GetProperty("source").GetString() + "\n\n" + response.GetProperty("text").GetString();
            status.Text = response.GetProperty("warning").GetString() ?? "Explicación lista. Consulta Cálculos del motor para contrastar los datos.";
            explanations.SelectedIndex = 1;
        });
    }

    private async Task DetectModelsAsync()
    {
        await RunTaskAsync("Buscando modelos locales…", async token =>
        {
            using HttpClient client = new(new HttpClientHandler { UseProxy = false }) { Timeout = TimeSpan.FromSeconds(5) };
            string json = await client.GetStringAsync("http://127.0.0.1:11434/api/tags", token);
            using JsonDocument document = JsonDocument.Parse(json);
            model.Items.Clear();
            model.Items.Add("Automático");
            foreach (JsonElement item in document.RootElement.GetProperty("models").EnumerateArray())
            {
                string name = item.GetProperty("name").GetString()!;
                if (!name.Contains("cloud", StringComparison.OrdinalIgnoreCase) && !item.TryGetProperty("remote_host", out _) && !item.TryGetProperty("remote_model", out _))
                    model.Items.Add(name);
            }
            model.SelectedIndex = 0;
            status.Text = model.Items.Count > 1 ? $"Ollama listo · {model.Items.Count - 1} modelo(s) local(es)." : "Ollama no tiene modelos locales. Consulta docs/analysis.md.";
        });
    }

    private Task ExportAsync()
    {
        if (outputDirectory is null) throw new InvalidOperationException("Todavía no hay un análisis guardado.");
        Process.Start(new ProcessStartInfo { FileName = outputDirectory, UseShellExecute = true });
        return Task.CompletedTask;
    }

    private async Task RunTaskAsync(string message, Func<CancellationToken, Task> action)
    {
        if (cancellation is not null) return;
        using CancellationTokenSource operation = new();
        cancellation = operation;
        foreach (Control control in lockedControls) control.Enabled = false;
        cancel.Enabled = true;
        status.Text = message;
        try { await action(operation.Token); }
        catch (OperationCanceledException) { if (!IsDisposed) status.Text = "Tarea cancelada. Puedes volver a analizar."; }
        catch (Exception error) { if (!IsDisposed) status.Text = "No se pudo completar: " + error.Message; }
        finally
        {
            cancellation = null;
            if (!IsDisposed)
            {
                foreach (Control control in lockedControls) control.Enabled = true;
                cancel.Enabled = false;
            }
        }
    }

    private async Task RunPythonAsync(IReadOnlyList<string> arguments, CancellationToken token)
    {
        token.ThrowIfCancellationRequested();
        ProcessStartInfo start = new(python) { WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8 };
        start.Environment["PYTHONUTF8"] = "1";
        start.Environment["PYTHONUNBUFFERED"] = "1";
        foreach (string argument in arguments) start.ArgumentList.Add(argument);
        using Process process = Process.Start(start) ?? throw new InvalidOperationException("No se pudo iniciar Python.");
        using CancellationTokenRegistration registration = token.Register(() =>
        {
            try { if (!process.HasExited) process.Kill(entireProcessTree: true); }
            catch (InvalidOperationException) { }
            catch (System.ComponentModel.Win32Exception) { }
        });
        Task<string> error = process.StandardError.ReadToEndAsync();
        Task output = DrainOutputAsync(process, arguments[0] == "tools/analysis_session.py");
        await process.WaitForExitAsync();
        string errors = await error;
        await output;
        token.ThrowIfCancellationRequested();
        if (process.ExitCode != 0) throw new InvalidOperationException(errors.Trim());
    }

    private async Task DrainOutputAsync(Process process, bool showProgress)
    {
        while (await process.StandardOutput.ReadLineAsync() is string line)
            if (showProgress && !IsDisposed && line.StartsWith("Analizando")) status.Text = line;
    }

    private static string Label(string? value) => value switch
    {
        "best" => "Buena", "good" => "Aceptable", "inaccuracy" => "Imprecisión", "mistake" => "Error", "blunder" => "Error grave", _ => value ?? ""
    };

    private static string Score(JsonElement value) => value.GetProperty("mate").ValueKind != JsonValueKind.Null
        ? $"Mate {value.GetProperty("mate")}" : (value.GetProperty("cp").GetInt32() / 100.0).ToString("+0.00;-0.00;0.00");

    private static string? ComponentLabel(string name) => name switch
    {
        "total" => "Total", "material" => "Material", "piece_square" => "Colocación", "mobility" => "Movilidad",
        "pawn_structure" => "Estructura de peones", "passed_pawns" => "Peones pasados", "bishop_pair" => "Pareja de alfiles",
        "rook_activity" => "Actividad de torres", "king_safety" => "Seguridad del rey", "space" => "Espacio", "tempo" => "Tempo", _ => null
    };
}

internal sealed class EvaluationChart : Control
{
    private double?[] values = [];
    private string[] labels = [];
    private int selectedIndex = -1;

    public EvaluationChart()
    {
        BackColor = Color.White;
        MinimumSize = new Size(0, 170);
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint |
                 ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
    }

    [System.ComponentModel.DesignerSerializationVisibility(
        System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    public int SelectedIndex
    {
        get => selectedIndex;
        set
        {
            selectedIndex = value;
            Invalidate();
        }
    }

    public void SetRecords(JsonElement[] records)
    {
        values = records.Select(ScoreFromWhitePerspective).ToArray();
        labels = records.Select(record =>
        {
            string prefix = record.GetProperty("move_number").GetInt32() +
                            (record.GetProperty("color").GetString() == "white" ? "." : "…");
            return prefix + record.GetProperty("move_san").GetString();
        }).ToArray();
        selectedIndex = -1;
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        e.Graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
        RectangleF plot = new(42, 14, Math.Max(1, ClientSize.Width - 56), Math.Max(1, ClientSize.Height - 42));
        using Font small = new("Segoe UI", 8);
        using Font title = new("Segoe UI", 8, FontStyle.Bold);
        using Pen axis = new(Color.FromArgb(180, 188, 184));
        using Pen grid = new(Color.FromArgb(225, 230, 227));
        using Pen zero = new(Color.FromArgb(130, 145, 138)) { DashStyle = System.Drawing.Drawing2D.DashStyle.Dash };
        using Brush text = new SolidBrush(Color.FromArgb(65, 75, 70));
        using Brush lineBrush = new SolidBrush(Color.FromArgb(42, 79, 70));
        using Pen line = new(Color.FromArgb(42, 79, 70), 2.2f);

        e.Graphics.DrawString("Evaluación desde la perspectiva de blancas (peones)", title, text, 42, 0);
        if (values.Length == 0)
        {
            e.Graphics.DrawString("Analiza una partida para ver la evolución.", small, text, plot.Left, plot.Top + 20);
            return;
        }

        double maximum = Math.Max(1, values.Where(value => value.HasValue)
            .Select(value => Math.Abs(value!.Value)).DefaultIfEmpty(1).Max());
        maximum = Math.Ceiling(maximum * 1.1);
        float zeroY = ValueY(0, maximum, plot);
        e.Graphics.DrawLine(axis, plot.Left, plot.Bottom, plot.Right, plot.Bottom);
        e.Graphics.DrawLine(axis, plot.Left, plot.Top, plot.Left, plot.Bottom);
        e.Graphics.DrawLine(zero, plot.Left, zeroY, plot.Right, zeroY);
        e.Graphics.DrawLine(grid, plot.Left, ValueY(maximum, maximum, plot), plot.Right, ValueY(maximum, maximum, plot));
        e.Graphics.DrawLine(grid, plot.Left, ValueY(-maximum, maximum, plot), plot.Right, ValueY(-maximum, maximum, plot));
        e.Graphics.DrawString($"+{maximum:0.0}", small, text, 2, plot.Top - 5);
        e.Graphics.DrawString("0.0", small, text, 14, zeroY - 7);
        e.Graphics.DrawString($"-{maximum:0.0}", small, text, 2, plot.Bottom - 8);

        PointF? previous = null;
        for (int index = 0; index < values.Length; index++)
        {
            if (!values[index].HasValue)
            {
                previous = null;
                continue;
            }
            PointF point = new(ValueX(index, values.Length, plot), ValueY(values[index]!.Value, maximum, plot));
            if (previous.HasValue) e.Graphics.DrawLine(line, previous.Value, point);
            float radius = index == selectedIndex ? 5 : 3;
            e.Graphics.FillEllipse(lineBrush, point.X - radius, point.Y - radius, radius * 2, radius * 2);
            if (index == selectedIndex)
            {
                e.Graphics.DrawLine(zero, point.X, plot.Top, point.X, plot.Bottom);
                string score = values[index]!.Value.ToString("+0.00;-0.00;0.00");
                string caption = labels[index] + "  " + score;
                e.Graphics.DrawString(caption, small, text,
                    Math.Clamp(point.X - 35, plot.Left, Math.Max(plot.Left, plot.Right - 120)),
                    Math.Max(plot.Top, point.Y - 25));
            }
            previous = point;
        }
        if (labels.Length > 0)
        {
            e.Graphics.DrawString(labels[0], small, text, plot.Left, plot.Bottom + 5);
            SizeF lastSize = e.Graphics.MeasureString(labels[^1], small);
            e.Graphics.DrawString(labels[^1], small, text, Math.Max(plot.Left, plot.Right - lastSize.Width), plot.Bottom + 5);
        }
    }

    private static float ValueX(int index, int count, RectangleF plot) =>
        count == 1 ? plot.Left + plot.Width / 2 : plot.Left + index * plot.Width / (count - 1);

    private static float ValueY(double value, double maximum, RectangleF plot) =>
        plot.Top + (float)((maximum - Math.Clamp(value, -maximum, maximum)) / (maximum * 2) * plot.Height);

    private static double? ScoreFromWhitePerspective(JsonElement record)
    {
        JsonElement score = record.GetProperty("played").GetProperty("score");
        double value;
        if (score.GetProperty("mate").ValueKind != JsonValueKind.Null)
            value = Math.Sign(score.GetProperty("mate").GetInt32()) * 10;
        else if (score.GetProperty("cp").ValueKind != JsonValueKind.Null)
            value = score.GetProperty("cp").GetInt32() / 100.0;
        else
            return null;
        return record.GetProperty("color").GetString() == "black" ? -value : value;
    }
}
