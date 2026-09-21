using ChessBotLauncher;

namespace ChessBotLauncher.Tests;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        string root = Path.GetFullPath(args.Length > 0 ? args[0] : ".");
        string output = Path.Combine(root, "build", "launcher-qa");
        Directory.CreateDirectory(output);
        using MainForm form = new(root);
        form.StartPosition = FormStartPosition.Manual;
        form.Location = new Point(-20000, -20000);
        form.ShowInTaskbar = false;
        int exitCode = 0;
        form.Shown += async (_, _) =>
        {
            try { await VerifyAsync(form, output); }
            catch (Exception error) { Console.Error.WriteLine(error); exitCode = 1; }
            finally { form.Close(); }
        };
        Application.Run(form);
        return exitCode;
    }

    private static async Task VerifyAsync(MainForm form, string output)
    {
        TabControl tabs = form.Controls.OfType<TabControl>().Single();
        AnalysisTab analysis = tabs.TabPages.OfType<AnalysisTab>().Single();
        tabs.SelectedTab = analysis;
        foreach (Size size in new[] { new Size(1040, 760), new Size(900, 690) })
        {
            form.Size = size;
            form.PerformLayout();
            using Bitmap image = new(form.Width, form.Height);
            form.DrawToBitmap(image, new Rectangle(Point.Empty, form.Size));
            image.Save(Path.Combine(output, $"analysis-{size.Width}.png"));
        }
        Control[] controls = Descendants(analysis).ToArray();
        Button analyze = controls.OfType<Button>().Single(b => b.Text == "Analizar");
        TextBox input = controls.OfType<TextBox>().Single(t => t.Multiline);
        DataGridView grid = controls.OfType<DataGridView>().Single();
        NumericUpDown analysisThreads = controls.OfType<NumericUpDown>().Single(n => n.Name == "analysisThreads");
        if (analysisThreads.Maximum != 256) throw new Exception("Wrong analysis thread range.");
        analysisThreads.Value = 2;
        input.Text = "1. e4 e5 2. Nf3 *";
        analyze.PerformClick();
        await WaitUntilAsync(() => analyze.Enabled, 60);
        if (grid.Rows.Count != 3) throw new Exception("PGN did not populate the analysis grid.");
        ChessBoard analysisBoard = controls.OfType<ChessBoard>().Single();
        if (grid.CurrentRow?.Index != 2 || analysisBoard.LastMove != "g1f3")
            throw new Exception("Analysis should open on and highlight the last move.");
        grid.CurrentCell = grid.Rows[1].Cells[0];
        CheckBox after = controls.OfType<CheckBox>().Single();
        if (!after.Checked) throw new Exception("Analysis should show the position after the selected move by default.");
        string boardFen = controls.OfType<ChessBoard>().Single().Position;
        if (!boardFen.Contains("4p3") || !boardFen.Contains(" w ")) throw new Exception("Wrong board after e5.");
        if (analysisBoard.LastMove != "e7e5") throw new Exception("Missing last move highlight.");
        if (!controls.OfType<Label>().Single(l => l.Name == "analysisLastMove").Text.Contains("1… e5"))
            throw new Exception("Wrong last-move caption.");
        after.Checked = false;
        if (analysisBoard.LastMove != "e2e4") throw new Exception("Before-move view should highlight the previous move.");
        after.Checked = true;
        Button chartToggle = controls.OfType<Button>().Single(b => b.Text.StartsWith("Gráfico de evaluación"));
        EvaluationChart chart = controls.OfType<EvaluationChart>().Single();
        chartToggle.PerformClick();
        if (!chart.Visible) throw new Exception("Evaluation chart did not expand.");
        ComboBox provider = controls.OfType<ComboBox>().Single(c => c.Items.Contains("Solo motor"));
        provider.SelectedIndex = 1;
        Button explain = controls.OfType<Button>().Single(b => b.Text == "Explicar / preguntar");
        explain.PerformClick();
        await WaitUntilAsync(() => explain.Enabled, 60);
        if (!controls.OfType<RichTextBox>().Any(t => t.Text.Contains("motor\n\n") && t.Text.Contains("negras")))
            throw new Exception("Deterministic explanation missing or wrong perspective.");
        form.Size = new Size(1040, 760);
        form.PerformLayout();
        using (Bitmap image = new(form.Width, form.Height))
        {
            form.DrawToBitmap(image, new Rectangle(Point.Empty, form.Size));
            image.Save(Path.Combine(output, "analysis-populated.png"));
        }
        NumericUpDown depth = controls.OfType<NumericUpDown>().Single(n => n.Maximum == 126);
        depth.Value = 20;
        analyze.PerformClick();
        Button cancel = controls.OfType<Button>().Single(b => b.Text == "Cancelar");
        await WaitUntilAsync(() => cancel.Enabled && grid.Enabled && grid.Rows.Count == 3 && grid.CurrentRow?.Index == 2, 10);
        grid.CurrentCell = grid.Rows[0].Cells[0];
        await WaitUntilAsync(() => controls.OfType<Label>().Any(l => l.Text.Contains("jugada 1")), 10);
        ComboBox lines = controls.OfType<ComboBox>().Single(c => c.Name == "analysisLines");
        await WaitUntilAsync(() => lines.Items.Count > 0, 10);
        if (analyze.Enabled) throw new Exception("Expected partial results while analysis is still active.");
        controls.OfType<Button>().Single(b => b.Text == "Ver línea").PerformClick();
        if (analysisBoard.LastMove is null) throw new Exception("Variation navigation should highlight its move.");
        controls.OfType<Button>().Single(b => b.Text == "Volver a partida").PerformClick();
        if (analysisBoard.LastMove != "e2e4") throw new Exception("Returning from the line lost the game position.");
        cancel.PerformClick();
        await WaitUntilAsync(() => analyze.Enabled, 10);
        if (!controls.OfType<Label>().Any(l => l.Text.Contains("cancelada"))) throw new Exception("Cancellation failed.");
        if (grid.Rows.Count != 3) throw new Exception("Cancellation lost the partial game.");
        explain.PerformClick();
        if (!controls.OfType<Label>().Any(l => l.Text.Contains("todavía no tiene un análisis completo")))
            throw new Exception("Incomplete results must not be sent to the explainer.");
        Console.WriteLine("PASS: live analysis, priority, partial results, last move, variation navigation and cancellation");
    }

    private static IEnumerable<Control> Descendants(Control parent) => parent.Controls.Cast<Control>()
        .SelectMany(child => new[] { child }.Concat(Descendants(child)));

    private static async Task WaitUntilAsync(Func<bool> condition, int seconds)
    {
        DateTime deadline = DateTime.UtcNow.AddSeconds(seconds);
        do
        {
            await Task.Delay(10);
            if (DateTime.UtcNow > deadline) throw new TimeoutException("Launcher operation timed out.");
        } while (!condition());
    }
}
