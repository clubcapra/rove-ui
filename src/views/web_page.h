#ifndef WEB_PAGE_H
#define WEB_PAGE_H

#include <QWidget>
#include <QWebEngineView>
#include <QVBoxLayout>
#include <QLineEdit>
#include <QToolBar>
#include <QAction>

class WebPage : public QWidget
{
    Q_OBJECT

public:
    explicit WebPage(QWidget* parent = nullptr);
    ~WebPage();

    void setUrl(const QString& url);
    QString url() const;

private slots:
    void onNavigate();
    void onBack();
    void onForward();
    void onRefresh();
    void onLoadFinished(bool ok);

signals:
    void elementHtmlRetrieved(const QString& id, const QString& html);
    void canvasDataUrlRetrieved(const QString& id, const QString& dataUrl);
    // Emitted when the underlying QWebEngineView finished loading a page
    void pageLoadFinished(bool ok);

private:
    QVBoxLayout* layout_;
    QWebEngineView* web_view_;
    QToolBar* toolbar_;
    QLineEdit* address_bar_;
    QAction* back_action_;
    QAction* forward_action_;
    QAction* refresh_action_;

};

#endif // WEB_PAGE_H
